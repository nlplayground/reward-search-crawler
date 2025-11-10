from extractor import Extractor
from rich import print
import json
from camoufox.async_api import AsyncCamoufox
from urllib.parse import urlencode
from utils.utils import date_add, deep_json_load
import os
import re


class CathayExtractor(Extractor):
    def __init__(self, proxy: str = None):
        super().__init__(proxy)
        self.phone = os.getenv("PHONE")
        self.password = os.getenv("PASSWORD")
        self.program = "Cathay"
        self.tab_id = ""
        self.base_url = "https://book.cathaypacific.com/CathayPacificAwardV3/dyn/air/booking/availability?TAB_ID="
        self.payload = {}
        self.ENC = ""
        self.login_url = "https://www.cathaypacific.com/cx/en_CN/sign-in.html?loginreferrer=https%3A%2F%2Fwww.cathaypacific.com%2Fcx%2Fen_CN%2Fbook-a-trip%2Fredeem-flights%2Fredeem-flight-awards.html"
    
    async def headers_from_browser(self, url, headless = True) -> dict:
        async with AsyncCamoufox(headless=headless, main_world_eval=True) as browser:
            page = await browser.new_page()

            headers = {
                "accept": "application/json, text/plain, */*",
                "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
                "content-type": "application/x-www-form-urlencoded",
                "priority": "u=1, i",
                "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "Referer": "https://book.cathaypacific.com/CathayPacificAwardV3/dyn/air/booking/availability",
                "Origin": "https://book.cathaypacific.com",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
            }
            self.session.headers.update(headers)
            await page.goto(url)
            await page.wait_for_selector('input[id^="react-aria"]', timeout=10000)
            await page.type('input[id^="react-aria"]', self.phone)
            await page.click('button.masterSignIn__submitBtn')
            await page.wait_for_selector('input#Password', timeout=10000)
            await page.type('input#Password', self.password)
            await page.click('button.masterSignIn__btn')
            await page.wait_for_load_state('networkidle')
            await page.goto(self.new_query_payload())
            await page.wait_for_timeout(25000)
            requestParams = await page.evaluate("mw:window.requestParams")
            
            if isinstance(requestParams, str):
                requestParams = json.loads(requestParams)
            self.tab_id = requestParams.get("TAB_ID", "")
            self.ENC = requestParams.get("ENC", "")
            requestParams.pop("SERVICE_ID", None)
            requestParams.pop("DIRECT_LOGIN", None)
            requestParams.pop("ENC", None)
            requestParams.pop("ENCT", None)
            self.payload = requestParams
            cookies = await page.context.cookies()
            for cookie in cookies:
                self.session.cookies.set(
                    name=cookie["name"],
                    value=cookie["value"],
                    domain=cookie.get("domain"),
                    path=cookie.get("path", "/")
                )

            return {
                    "tab_id": self.tab_id,
                    "cookies": self.session.cookies["JSESSIONID_CathayPacificAwardV3"]
                }

    async def search_flights_for_date(self, origin: str, destination: str, date: str) -> list:
        max_retries = 3
        retries = 0
        try:
            while retries < max_retries:
                async with self.limiter:
                    self.payload.update({
                        "B_DATE_1": date.replace("-", "") + "0000",
                        "B_LOCATION_1": origin,
                        "E_LOCATION_1": destination,
                    })
                    encoded_data = "&".join(f"{k}={v}" for k, v in self.payload.items())
                    resp = await self.session.post(
                        url=self.base_url + self.tab_id,
                        data=encoded_data,
                    )

                    if resp.status_code < 300 and resp.status_code != 404:
                        return await self.extract_offers(resp.json(), origin, destination, date)

                    tab_result = await self.new_tab_id()
                    if tab_result is None:
                        print("Failed to get new TAB_ID, aborting retry.")
                        break
                    retries += 1
        except Exception as e:
            print(f"Error CX fetching for {origin} → {destination} on {date}:{type(e)}: {e}")
            await self.headers_from_browser(self.login_url)
            return []
            
            
        
    def new_query_payload(
        self,
        route={"from": "ITM", "to": "HND", "date": None},
        passengers={"adult": 1, "child": 0},
        cabinclass="Y",
        oneway=False,
        flexible="false",
        lang={"el": "en", "ec": "HK"}
    ):
        if route.get("date") is None:
            route["date"] = date_add(1)

        base_url = "https://api.cathaypacific.com/redibe/IBEFacade"

        params = {
            "ACTION": "RED_AWARD_SEARCH",
            "ENTRYPOINT": f"https://www.cathaypacific.com/cx/{lang['el']}_{lang['ec']}/book-a-trip/redeem-flights/redeem-flight-awards.html",
            "ENTRYLANGUAGE": lang["el"],
            "ENTRYCOUNTRY": lang["ec"],
            "RETURNURL": f"https://www.cathaypacific.com/cx/{lang['el']}_{lang['ec']}/book-a-trip/redeem-flights/redeem-flight-awards.html?recent_search=ow",
            "ERRORURL": f"https://www.cathaypacific.com/cx/{lang['el']}_{lang['ec']}/book-a-trip/redeem-flights/redeem-flight-awards.html?recent_search=ow",
            "CABINCLASS": cabinclass,
            "BRAND": "CX",
            "ADULT": passengers.get("adult", 1),
            "CHILD": passengers.get("child", 0),
            "FLEXIBLEDATE": flexible,
            "ORIGIN[1]": route["from"],
            "DESTINATION[1]": route["to"],
            "DEPARTUREDATE[1]": route["date"],
            "LOGINURL": (
                f"https://www.cathaypacific.com/cx/{lang['el']}_{lang['ec']}/sign-in/campaigns/miles-flight.html?"
                f"loginreferrer=https%3A%2F%2Fwww.cathaypacific.com%2Fcx%2F{lang['el']}_{lang['ec']}%2Fbook-a-trip%2Fredeem-flights%2Fredeem-flight-awards.html"
                "%3Fauto_submit%3Dtrue%26recent_search%3Dow%26vs%3D2"
            ),
        }

        full_url = f"{base_url}?{urlencode(params)}"
        return full_url
    
    async def log_request(self, request):        
        pass
    async def log_response(self, response):
        pass
    
    async def get_milesInfo(self, mile_keys):
        url = "https://api.cathaypacific.com/redibe/milesInfo/v2.0"
        data = {
            "milesInfoList": [mile_keys]
        }
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8,zh-CN;q=0.7,zh;q=0.6',
            'content-type': 'application/json',
            'origin': 'https://book.cathaypacific.com',
            'priority': 'u=1, i',
            'referer': 'https://book.cathaypacific.com/',
            'sec-ch-ua': '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
        }
        resp = await self.session.post(url,headers=headers, json=data)
        # text = await resp.text()
        return resp.json()['milesInfo']
        

    async def extract_offers(self, data, origin, destination, date):
        res_data = deep_json_load(data)
        pageBom = res_data.get("pageBom", "{}")
        results = []
        if pageBom.get("modelObject", {}).get("isContainingErrors"):
            print("Error:", pageBom["modelObject"].get("messages", [{}])[0].get("text"))
            return

        availabilities = pageBom["modelObject"].get("availabilities", {})
        upsell_bounds = availabilities.get("upsell", {}).get("bounds", [])
        if upsell_bounds:
            flights = upsell_bounds[0].get("flights", [])
            for flight in flights:
                if flight["bookable"]:
                    seg1 = flight["segments"][0]
                    cabins1 = seg1.get("cabins", {})
                    f1 = cabins1.get("F", {}).get("status", 'C')
                    j1 = cabins1.get("B", {}).get("status", 'C')

                    if not (str(f1).isdigit() or str(j1).isdigit()):
                        continue

                    leg1_airline = seg1["flightIdentifier"]["marketingAirline"]
                    leg1_flight_no = seg1["flightIdentifier"]["flightNumber"]
                    
                    if len(flight["segments"]) == 1:
                        flightData = f"{leg1_airline}{leg1_flight_no}"
                        cabin_class = "Bus" if str(j1).isdigit() else "First"
                        flightId = flight["flightIdString"][:-3] + ("BUS" if str(j1).isdigit() else "FIR")
                        mileInfo = await self.get_milesInfo(flightId)
                        results.append({
                            "origin": origin,
                            "destination": destination,
                            "date": date,
                            "cabin": cabin_class,
                            "points": mileInfo[flightId],
                            "route": flightData,
                            "stops": len(flight["segments"]) - 1,
                            "program": self.program
                        })
                    else:
                        seg2 = flight["segments"][1]
                        cabins2 = seg2.get("cabins", {})
                        f2 = cabins2.get("F", {}).get("status", 'C')
                        j2 = cabins2.get("B", {}).get("status", 'C')
                        if not (str(f2).isdigit() or str(j2).isdigit()):
                            continue

                        leg2_airline = seg2["flightIdentifier"]["marketingAirline"]
                        leg2_flight_no = seg2["flightIdentifier"]["flightNumber"]

                        stop_match = re.search(r"^[A-Z]{3}:([A-Z:]{3,7}):[A-Z]{3}_", flight["flightIdString"])
                        stopcity = stop_match.group(1).replace(":", " / ") if stop_match else ""

                        flightData = f"{leg1_airline}{leg1_flight_no}_{stopcity}_{leg2_airline}{leg2_flight_no}"
                        cabin_class = "Bus" if str(j1).isdigit() else "First"
                        flightId = flight["flightIdString"][:-3] + ("BUS" if str(j1).isdigit() else "FIR")
                        mileInfo = await self.get_milesInfo(flightId)
                        results.append({
                            "origin": origin,
                            "destination": destination,
                            "date": date,
                            "cabin": cabin_class,
                            "points": mileInfo[flightId],
                            "route": flightData,
                            "stops": len(flight["segments"]) - 1,
                            "program": self.program
                        })

        return results
    
    async def new_tab_id(self) -> str | None:
        if not self.ENC:
            print("Error: No ENC found in request_params.")
            return None

        parameters = {
            "SERVICE_ID": "1",
            "LANGUAGE": "TW",
            "EMBEDDED_TRANSACTION": "AirAvailabilityServlet",
            "SITE": "CXAWCXAW",
            "ENC": self.ENC,
            "ENCT": "2",
            "ENTRYCOUNTRY": "",
            "ENTRYLANGUAGE": "",
        }

        url = "https://book.cathaypacific.com/CathayPacificAwardV3/dyn/air/booking/availability"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "accept": "application/json, text/plain, */*",
            }

        try:
            response = await self.session.post(url, data=parameters, headers=headers)
        except Exception as e:
            print(f"Request failed: {e}")
            await self.headers_from_browser(self.login_url)
            return None

        if response.status_code != 200:
            print(f"Failed to receive Tab ID (HTTP {response.status_code}).")
            await self.headers_from_browser(self.login_url)
            return None

        try:
            data = response.json()
            deep_data = deep_json_load(data)
        
        except Exception as e:
            print("fail parsing response:", e)
            await self.headers_from_browser(self.login_url)
            return None


        match = deep_data.get("requestParams", None)
        
        if not match:
            print("Could not parse requestParams. Re-login")
            await self.headers_from_browser(self.login_url)

            return None

        tab_id = match.get("TAB_ID")
        if not tab_id:
            print("No TAB_ID found in requestParams.")
            await self.headers_from_browser(self.login_url)
            return None

        self.tab_id = tab_id
        return tab_id
