from extractor import Extractor
from typing import List
from rich import print
import httpx
import asyncio


class VirginExtractor(Extractor):
    def __init__(self, proxy: str = None):
        super().__init__(proxy)
        self.program = "VA"
        self.base_url = "https://book.virginaustralia.com"
        self.graphql_url = f"{self.base_url}/api/graphql"
        self.login_url = "https://book.virginaustralia.com/dx/VADX/1"
        self.refresh_lock = asyncio.Lock()
        self.refresh_condition = asyncio.Condition()
        self.is_refreshing = False
    
    async def headers_from_browser(self, url, headless = "virtual") -> dict:
        await super().headers_from_browser(url, headless)

        self.session.headers.update({
            "x-sabre-storefront": "VADX",
            "Content-Type": "application/json",
        })
        return self.session.headers, self.session.cookies

    async def preflight_check(self):
        from datetime import date, timedelta
        today = date.today()
        dt =  (today + timedelta(days=2)).isoformat()
        while True:
            resp = await self._fetch_flights_once("MEL", "SYD", dt)
            if not resp or resp.status_code >= 400:
                print('invalid cookie, re login')
                await self.headers_from_browser(self.login_url, "virtual")
            else:
                break

    async def search_flights_for_date(
        self, origin: str, destination: str, date: str
    ) -> List[dict]:
        async with self.limiter:
            json_data = {
                'operationName': 'bookingAirSearch',
                'variables': {
                    'airSearchInput': {
                        'cabinClass': 'Business',
                        'awardBooking': True,
                        'promoCodes': [],
                        'searchType': 'BRANDED',
                        'itineraryParts': [
                            {
                                'from': {
                                    'useNearbyLocations': False,
                                    'code': origin,
                                },
                                'to': {
                                    'useNearbyLocations': False,
                                    'code': destination,
                                },
                                'when': {
                                    'date': date,
                                },
                            },
                        ],
                        'passengers': {
                            'ADT': 1,
                        },
                    },
                },
                'extensions': {},
                'query': 'query bookingAirSearch($airSearchInput: CustomAirSearchInput) {\n                bookingAirSearch(airSearchInput: $airSearchInput) {\n                    originalResponse\n                    __typename\n                }\n            }',
            }

            try:
                response = await self.session.post(
                    self.graphql_url,
                    json=json_data,
                )
                if response.status_code > 400:
                    await self.headers_from_browser(self.login_url, "virtual")
                    await self.preflight_check()
                    response = await self.session.post(
                        self.graphql_url,
                        json=json_data,
                        # timeout=10
                    )
                data = response.json()
                origin_offers = data.get('data', {}).get('bookingAirSearch', {}).get('originalResponse', {}).get('unbundledOffers', [])
                resolved = self.resolve_refs(origin_offers)
                results = self.extract_offers(resolved, origin, destination, date)

                return results
            
            except httpx.ReadTimeout as e:
                print(f"Timeout VA fetching for {origin} → {destination} on {date}: {e}")
                await self.headers_from_browser(self.login_url, "virtual")
                await self.preflight_check()
                return []
            except Exception as e:
                print(f"Error VA fetching for {origin} → {destination} on {date}:{type(e)}: {e}")
                await self.headers_from_browser(self.login_url, "virtual")
                await self.preflight_check()
                return []

    def resolve_refs(self, obj):
        id_map = {}

        def collect(o):
            if isinstance(o, dict):
                if "@id" in o:
                    id_map[o["@id"]] = o
                for v in o.values():
                    collect(v)
            elif isinstance(o, list):
                for v in o:
                    collect(v)

        def deref(o):
            if isinstance(o, dict):
                if "@ref" in o:
                    return deref(id_map[o["@ref"]])
                return {k: deref(v) for k, v in o.items()}
            elif isinstance(o, list):
                return [deref(v) for v in o]
            else:
                return o

        collect(obj)
        return deref(obj)

    def extract_offers(self, offers, origin, destination, date):
        results = []

        for date_offers in offers:
            for offer in date_offers:
                if not offer:
                    continue

                if not offer.get("offerInformation", {}).get("negotiated", False):
                    continue

                cabin = offer.get("cabinClass")[:3]
                fare_alt = (
                    offer.get("fare", {})
                        .get("alternatives", [[[]]])[0][0]
                    if offer.get("fare", {}).get("alternatives")
                    else None
                )
                parts = offer.get("itineraryPart", []) or []
                segs_str = ""
                stops = 0
                valid_route = False

                for part in parts:
                    segments = [
                        seg for seg in (part.get("segments") or [])
                        if seg.get("origin")
                        and seg.get("destination")
                        and seg.get("flight")
                        and seg["flight"].get("airlineCode")
                        and seg["flight"].get("flightNumber")
                    ]
                    if not segments:
                        continue
                    stops += len(segments) - 1

                    first_seg = segments[0]
                    last_seg = segments[-1]
                    if first_seg["origin"] != origin or last_seg["destination"] != destination:
                        continue

                    if len(segments) == 1:
                        seg = segments[0]
                        segs_str = f"{seg['flight']['airlineCode']}{seg['flight']['flightNumber']}"
                    else:
                        first_seg = segments[0]
                        segs = [f"{first_seg['flight']['airlineCode']}{first_seg['flight']['flightNumber']}"]
                        for seg in segments[1:]:
                            segs.append(f"{seg['origin']}_{seg['flight']['airlineCode']}{seg['flight']['flightNumber']}")

                        segs_str = "_".join(segs)

                    valid_route = True

                if not valid_route:
                    continue

                if fare_alt:
                    results.append({
                        "origin": origin,
                        "destination": destination,
                        "date": (offer.get("departureDates") or [date])[0],
                        "cabin": cabin,
                        "points": fare_alt.get("amount"),
                        "route": segs_str,
                        "stops": stops,
                        "program": self.program 
                    })

        return results

    async def log_request(self, request):        
        pass
    async def log_response(self, response):
        pass
    async def _fetch_flights_once(self, origin: str, destination: str, date: str) -> httpx.Response:
        """Make one raw GraphQL request — no retries, no recursion."""
        try:
            json_data = {
                'operationName': 'bookingAirSearch',
                'variables': {
                    'airSearchInput': {
                        'cabinClass': 'Business',
                        'awardBooking': True,
                        'promoCodes': [],
                        'searchType': 'BRANDED',
                        'itineraryParts': [{
                            'from': {'useNearbyLocations': False, 'code': origin},
                            'to': {'useNearbyLocations': False, 'code': destination},
                            'when': {'date': date},
                        }],
                        'passengers': {'ADT': 1},
                    },
                },
                'extensions': {},
                'query': 'query bookingAirSearch($airSearchInput: CustomAirSearchInput) {\nbookingAirSearch(airSearchInput: $airSearchInput) {\noriginalResponse\n__typename\n}\n}',
            }

            return await self.session.post(self.graphql_url, json=json_data)
        except Exception as e:
            print(f"Error VA fetching for {origin} → {destination} on {date}:{type(e)}: {e}")
            return None
