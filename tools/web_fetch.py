import json
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from tools.scraping import fetch_with_fallback

_LINK_KEYWORDS = ("about", "contact", "team", "services", "location")


def fetch_webpage_text(url: str) -> str:
    """
    Fetch a webpage and return its title, meta description, visible text (truncated),
    and links whose text or href suggest they lead to About/Contact/Services pages.

    Uses a multi-engine fallback chain (requests -> Scrapling -> Crawl4AI -> Playwright)
    so JavaScript-rendered pages still work, bounded by SCRAPER_MAX_ATTEMPTS.

    Args:
        url (str): The webpage URL to fetch.

    Returns:
        str: JSON string with keys: title, meta_description, text, internal_links.
    """
    result = fetch_with_fallback(url)
    if not result.success or not result.html:
        return json.dumps({"error": f"Could not fetch {url}: {result.error}"})

    soup = BeautifulSoup(result.html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag and meta_tag.get("content"):
        meta_desc = meta_tag["content"].strip()

    # Kept small on purpose: tool results are resent in full on every subsequent
    # turn of the agent's tool-calling loop, so verbose payloads compound quickly
    # into context-window overflows.
    text = " ".join(soup.get_text(separator=" ").split())[:1500]

    internal_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        label = a.get_text(strip=True).lower()
        if any(k in href.lower() or k in label for k in _LINK_KEYWORDS):
            internal_links.append(urljoin(url, href))

    return json.dumps(
        {
            "title": title,
            "meta_description": meta_desc,
            "text": text,
            "internal_links": list(dict.fromkeys(internal_links))[:6],
        }
    )
