from extractor import Extractor
from utils.date_range import date_range
from typing import Dict, Any, List
import requests


class VirginExtractor(Extractor):
    def __init__(self, proxy: str = None):
        super().__init__(proxy)
    
    def search_flights_for_date(
        self, origin: str, destination: str, date: str
    ) -> List[dict]:
        payload = {
            "operationName": "bookingAirSearch",
            "variables": {
                "airSearchInput": {
                    "cabinClass": "Business",
                    "awardBooking": True,
                    "promoCodes": [],
                    "searchType": "BRANDED",
                    "itineraryParts": [
                        {
                            "from": {"useNearbyLocations": False, "code": origin},
                            "to": {"useNearbyLocations": False, "code": destination},
                            "when": {"date": date}
                        }
                    ],
                    "passengers": {"ADT": 1}
                }
            },
            "extensions": {},
            "query": """query bookingAirSearch($airSearchInput: CustomAirSearchInput) {
                bookingAirSearch(airSearchInput: $airSearchInput) {
                    originalResponse
                    __typename
                }
            }"""
        }


        try:
            response = self.session.post(
                self.graphql_url,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            origin_offers = data.get('data', {}).get('bookingAirSearch', {}).get('originalResponse', {}).get('unbundledOffers', [])
            # Use resolve_refs and extract_offers as in your test.py
            resolved = self.resolve_refs(origin_offers)
            return self.extract_offers(resolved, origin, destination, date)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching for {origin} → {destination} on {date}: {e}")
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

                # Only consider negotiated offers
                if not offer.get("offerInformation", {}).get("negotiated", False):
                    continue

                cabin = offer.get("cabinClass")
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

                    segs = [
                        f"{seg['origin']} ({seg['flight']['airlineCode']}{seg['flight']['flightNumber']})"
                        for seg in segments
                    ]
                    segs.append(f"{last_seg['destination']} ({last_seg['flight']['airlineCode']}{last_seg['flight']['flightNumber']})")
                    segs_str = " -> ".join(segs)
                    valid_route = True

                if not valid_route:
                    continue

                # Filtering by stop conditions
                if (origin == "SIN" and stops > 0) or (destination == "SIN" and stops > 0):
                    continue
                if stops > 1:
                    continue

                if fare_alt:
                    results.append({
                        "origin": origin,
                        "destination": destination,
                        "date": (offer.get("departureDates") or [date])[0],
                        "cabin": cabin,
                        "amount": fare_alt.get("amount"),
                        "route": segs_str,
                        "stops": stops,
                    })

        return results

    def scrape(self, origins: List[str], destinations: List[str]):
        all_results = []
        for origin in origins:
            for destination in destinations:
                for d in date_range(days=360):
                    offers = self.search_flights_for_date(origin, destination, d)
                    all_results.extend(offers)
                    print(offers)
        return all_results