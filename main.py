from virgin_extractor import VirginExtractor
from cathay_extractor import CathayExtractor
from qantas_extractor import QantasExtractor
import asyncio
from rich import print
import os
from dotenv import load_dotenv

async def main():
    load_dotenv()
    start_day = int(os.getenv("START_DAY"))
    end_day = int(os.getenv("END_DAY"))
    origins = os.getenv("ORIGINS").split(",")
    destinations = os.getenv("DESTINATIONS").split(",")

    qantas = QantasExtractor()
    await qantas.headers_from_browser(headless=True)

    virgin = VirginExtractor()
    virgin_url = "https://book.virginaustralia.com/dx/VADX/1"
    await virgin.headers_from_browser(virgin_url, "virtual")
    await virgin.preflight_check()

    cathay = CathayExtractor()
    cathay_url = "https://www.cathaypacific.com/cx/en_CN/sign-in.html?loginreferrer=https%3A%2F%2Fwww.cathaypacific.com%2Fcx%2Fen_CN%2Fbook-a-trip%2Fredeem-flights%2Fredeem-flight-awards.html"
    await cathay.headers_from_browser(cathay_url, True)

    try:
        results = await asyncio.gather(
            virgin.crawl(origins=origins, destinations=destinations, start_day=start_day, end_day=end_day),
            cathay.crawl(origins, destinations, start_day=start_day, end_day=end_day),
            qantas.crawl(origins,destinations, start_day=start_day, end_day=end_day),
            return_exceptions=True
        )
    except Exception as e:
        print("[red]Gather failed:", repr(e))
        results = []

    return results

if __name__ == "__main__":
    results = asyncio.run(main())
