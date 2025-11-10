from camoufox.async_api import AsyncCamoufox
from rich import print
from utils.utils import date_range
from aiolimiter import AsyncLimiter
from typing import List
from curl_cffi import AsyncSession, CurlHttpVersion
from google.cloud import storage
import json
from datetime import datetime


class Extractor:
    def __init__(self, proxy: str = None):
        self.session = AsyncSession(impersonate="firefox135", default_headers=True, http_version=CurlHttpVersion.V1_1)
        if proxy:
            self.session.proxies.update({
                "http": proxy,
                "https": proxy,
            })
        self.limiter = AsyncLimiter(max_rate=40)
        self.login_url = ""
        self.program = ""
        self.storage_client = storage.Client()
        self.bucket_name = "reward-flight-results"
        self.bucket = self.storage_client.bucket(self.bucket_name)

    async def search_flights_for_date(self, origin: str, destination: str, date: str) -> list:
        NotImplementedError("This method should be implemented by subclasses.")

    async def headers_from_browser(self, url = None, headless = True) -> dict:
        if not url:
            url = self.login_url
        async with AsyncCamoufox(headless=headless, os="linux") as browser:
            print("login to virgin")
            page = await browser.new_page()

            request_headers = {}

            async def handler_request(request):
                nonlocal request_headers
                request_headers = request.headers
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

            page.on("request", handler_request)

            await page.goto(url)
            await page.wait_for_timeout(10000)
            cookies = await page.context.cookies()
            for cookie in cookies:
                self.session.cookies.set(
                    name=cookie["name"],
                    value=cookie["value"],
                    domain=cookie.get("domain"),
                    path=cookie.get("path", "/")
                )

            return self.session.headers
    
    def get(self,url, headers=None):
        response = self.session.get(url, headers=headers)
        return response
    
    async def log_request(self, request):        
        print(f"Request: {request.method} {request.url}")

    async def log_response(self, response):
        request = response.request
        print(f"Request: {request.method} {request.url} - Status: {response.status_code}")

    async def save_to_gcs(self, data, origin, destination, date):
        """Save results to Google Cloud Storage bucket"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        blob_name = f"{self.program}/{date}_{origin}_{destination}.json"
        blob = self.bucket.blob(blob_name)
        
        # Convert data to JSON string
        json_data = json.dumps(data, default=str)
        blob.upload_from_string(json_data, content_type='application/json')
        
        return blob_name

    async def crawl(self, origins: List[str], destinations: List[str], start_day: int = 0, end_day: int = 360):
        all_results = []
        for d in date_range(days=360, start=start_day, end=end_day):
            for origin in origins:
                for destination in destinations:
                    try:
                        # print(f"Fetching {origin} -> {destination} on {d} for {self.program}")
                        result = await self.search_flights_for_date(origin, destination, d)
                        if result:
                            all_results.extend(result)
                            # Save to GCS bucket
                            blob_name = await self.save_to_gcs(result, origin, destination, d)
                            print(f"Saved to GCS: {blob_name}")
                        # print(f"Fetched {result} for {origin} -> {destination} on {d} for {self.program}")
                    except Exception as e:
                        print(f"{self.program} Error fetching {origin} -> {destination} on {d}: {e}")
                    

        print(f"✅ {self.program}, all_results: {len(all_results)}")
        return all_results