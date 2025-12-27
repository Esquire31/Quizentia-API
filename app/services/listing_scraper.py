import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

BASE_URL = "https://www.livelaw.in"
LISTING_URL = f"{BASE_URL}/articles"


def get_latest_article_urls(limit: int = 12) -> list[str]:
    response = requests.get(LISTING_URL, headers=HEADERS, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")

    urls = []
    seen = set()

    cards = soup.select("div.sup_crt_col_border_bottom.grid_page")

    for card in cards:
        link = card.find("a", href=True)
        if not link:
            continue

        href = link["href"].strip()

        full_url = urljoin(BASE_URL, href)

        # Deduplicate
        if full_url in seen:
            continue

        seen.add(full_url)
        urls.append(full_url)

        if len(urls) == limit:
            break

    return urls
