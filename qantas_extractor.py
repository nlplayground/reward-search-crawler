from extractor import Extractor
from typing import List
from rich import print
import httpx
from datetime import date, timedelta
from urllib.parse import urlencode, parse_qsl
from datetime import datetime
from curl_cffi import AsyncSession, CurlHttpVersion



from camoufox.async_api import AsyncCamoufox

class QantasExtractor(Extractor):
    def __init__(self, proxy: str = None):
        super().__init__(proxy)
        self.program = "QF"
        self.login_url = "https://www.qantas.com/en-au"
        self.search_url = ""
        self.search_body = ""
        self.no_results_cache = set()
        self.session = AsyncSession(impersonate="firefox135", default_headers=True, http_version=CurlHttpVersion.V2_0)

    def mark_7days_no_results(self, origin, destination, start_date_str):
        """Mark 7 days starting from start_date_str as no results."""
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        for i in range(7):
            day = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            self.no_results_cache.add((origin, destination, day))

    def update_search_body(self, search_body: str, **updates) -> str:
        params = dict(parse_qsl(search_body))
        for key, value in updates.items():
            if key in params:
                params[key] = value

        return urlencode(params)
    def generate_login_url(
        self,
        departure_airport="SYD",
        arrival_airport="MEL",
        use_points=True,
        trip_type="O",
        flexible_with_dates=True,
        travel_class="BUS",
        adults=1
    ):
        base_url = "https://www.qantas.com/en-au/book/flights"
        departure_date = (date.today() + timedelta(days=1)).isoformat()

        params = {
            "departureAirportCode": departure_airport,
            "arrivalAirportCode": arrival_airport,
            "departureDate": departure_date,
            "usePoints": str(use_points).lower(),
            "tripType": trip_type,
            "flexibleWithDates": str(flexible_with_dates).lower(),
            "travelClass": travel_class,
            "adults": adults
        }

        return f"{base_url}?{urlencode(params)}"

    async def headers_from_browser(self, url = None, headless = True) -> dict:
        async with AsyncCamoufox(os=["windows", "macos", "linux"],
                                 headless=headless, 
                                #  main_world_eval=True,
                                 humanize=True,
                                 geoip=True,
            ) as browser:
            page = await browser.new_page()
            url = self.generate_login_url()
            async def handler_request(req):
                if (
                    req.method == "POST"
                    and "upsellUpdateAction" in req.url
                ):
                    # parsed = urlparse(req.url)
                    # params = parse_qs(parsed.query)
                    # tab_id = params.get("TAB_ID", ["?"])[0]
                    post_data = req.post_data or "(no body)"
                    # print(f"\n🎯 MATCHED REQUEST")
                    # print(f"HEADERS: {req.headers}")
                    # print(f"URL: {req.url}")
                    # print(f"TAB_ID: {tab_id}")
                    # print(f"BODY:\n{post_data}\n")
                    request_headers = req.headers
                    for key, value in request_headers.items():
                        if key.lower() not in [
                            "content-length",
                            "transfer-encoding",
                            "set-cookie",
                            "cookie",
                            "upgrade-insecure-requests",
                            "authorization",
                            "host"
                            
                        ]:
                            self.session.headers.update({key: value})
                    self.search_body = post_data
                    self.search_url = req.url

            page.on("request", handler_request)
            # print(url)
            await page.goto(url)
            await page.wait_for_timeout(5000)
            await page.click('button.css-12vflty-baseStyles-solidStyles-Button')
            await page.wait_for_timeout(25000)
            print("On search page.")
            await page.click('button#e2e-tab-date-0-8')
            await page.wait_for_timeout(5000)
            cookies = await page.context.cookies()
            for cookie in cookies:
                self.session.cookies.set(
                    name=cookie["name"],
                    value=cookie["value"],
                    domain=cookie.get("domain"),
                    path=cookie.get("path", "/")
                )

            return self.session.headers

    async def search_flights_for_date(
        self, origin: str, destination: str, date: str) -> List[dict]:
        if (origin, destination, date) in self.no_results_cache:
            return []
        async with self.limiter:
            data = self.update_search_body(
                self.search_body,
                B_DATE_1=date.replace("-", "") + "0000",
                B_LOCATION_1=origin,
                E_LOCATION_1=destination,
                )
            try:
                response = await self.session.post(
                    self.search_url,
                    data=data,
                )
                results = []
                data = response.json().get('modelInput', {})
                if data.get('pageCode') == "FFCO":
                    bounds = data.get('availability', {}).get('bounds', [])
                    if not bounds:
                        return 

                    bound = bounds[0]
                    flights = bound.get('flights', {})
                    if flights:
                        itineraries = bound.get('listItineraries', {}).get('itineraries', [])
                    else:
                        return
                    for item_id, flight in flights.items():
                        rec = flight.get('listRecommendation', {}).get('ACEBUS')
                        if not rec or rec.get('isRewardPlus'):
                            continue
                        else:
                            points = rec.get('priceForAll', {}).get('convertedBaseFare', '')

                        itinerary = next((it for it in itineraries if it.get('itemId') == item_id), None)
                        if not itinerary:
                            continue

                        segments = itinerary.get('segments', [])
                        if not segments:
                            continue
                        parts = []
                        for i, seg in enumerate(segments):
                            airline = seg.get('codeForIcon', '')
                            flight_no = seg.get('flightNumber', '')
                            parts.append(f"{airline}{flight_no}")
                            if i < len(segments) - 1:
                                stop_city = seg.get('endLocationCode', '')[:3]
                                parts.append(stop_city)

                        flight_data = "_".join(filter(None, parts))  # join and skip blanks
                        results.append({
                            "origin": origin,
                            "destination": destination,
                            "date": date,
                            "cabin": "Bus",
                            "points": points,
                            "route": flight_data,
                            "stops": len(segments) - 1,
                            "program": self.program
                        })
                else:
                    if data.get('pageCode') != "GERR":
                        self.mark_7days_no_results(origin, destination, date)
                    else:
                        await self.headers_from_browser(headless=True)
                return results
            
            except httpx.TimeoutException as e:
                print(f"Timeout QF fetching for {origin} → {destination} on {date}: {e}")
                await self.headers_from_browser(headless=True)
                return []
            except Exception as e:
                print(f"Error QF fetching for {origin} → {destination} on {date}:{type(e)}: {e}")
                await self.headers_from_browser(headless=True)
                return []

    async def log_request(self, request):        
        pass
    async def log_response(self, response):
        pass