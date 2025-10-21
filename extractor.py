from camoufox.sync_api import Camoufox
import requests
from rich import print
import os

class Extractor:
    def __init__(self, proxy: str = None):
        self.session = requests.Session()
        if proxy:
            self.session.proxies.update({
                "http": proxy,
                "https": proxy,
            })
    def headers_from_browser(self, url) -> dict:
        with Camoufox(headless=True) as browser:
            page = browser.new_page()
            def handler_request(request):
                global request_headers
                request_headers = request.headers
                for key, value in request_headers.items():
                    if key.lower() not in [
                        "content-length",
                        "transfer-encoding",
                        "set-cookie",
                    ]:
                        self.session.headers.update({key: value})

    
            page.on("request", handler_request)
            page.goto(url)
            page.wait_for_timeout(5000)  # Wait for 5 seconds to ensure all
            print("session headers", request_headers)
    
    def get(self,url, headers=None):
        response = self.session.get(url, headers=headers)
        return response
    
    