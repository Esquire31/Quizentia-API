import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def scrape_article(url: str) -> dict:
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")

    # Extract title
    title_tag = soup.find("h1")
    if not title_tag:
        raise Exception("Title not found")

    title = title_tag.get_text(strip=True)

    # Extract article content
    article_div = soup.select_one("div.details-story-wrapper")
    if not article_div:
        raise Exception("Article container not found")

    paragraphs = article_div.select("p")

    content = [
        p.get_text(strip=True)
        for p in paragraphs
        if p.get_text(strip=True)
    ]

    return {
        "title": title,
        "content": content,
        "full_text": "\n".join(content)
    }
