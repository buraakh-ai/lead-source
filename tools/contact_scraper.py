import json
from urllib.parse import urlparse

from tools.contact_extraction import extract_contacts
from tools.scraping import fetch_with_fallback


def scrape_contacts(url: str) -> str:
    """
    Scrape a webpage for lead contact details: emails and phone numbers from
    schema.org JSON-LD structured data, the page footer (mailto:/tel: links and
    text), and - only if those find nothing - a broader scan of the whole page
    (mailto:/tel: links and page text) plus LinkedIn URLs. If still nothing useful
    is found, follows same-site About/Contact/Team links one level deep.

    Uses a multi-engine fallback chain (requests -> Scrapling -> Crawl4AI ->
    Playwright) so JavaScript-rendered pages still work, bounded by
    SCRAPER_MAX_ATTEMPTS.

    Args:
        url (str): The URL of the small business webpage to scrape.

    Returns:
        str: JSON string with keys: url, page_title, emails, phones, linkedin_urls,
             candidate_name_hints (short heading text near contact info, may indicate a
             person's or business's name).
    """
    result = fetch_with_fallback(url)
    if not result.success or not result.html:
        return json.dumps({"url": url, "error": f"Could not fetch page: {result.error}"})

    data = extract_contacts(result.html, url)

    if not data["emails"] and not data["phones"] and not data["linkedin_urls"]:
        for link in data["follow_links"]:
            if urlparse(link).netloc != urlparse(url).netloc:
                continue
            sub_result = fetch_with_fallback(link)
            if not sub_result.success or not sub_result.html:
                continue
            sub_data = extract_contacts(sub_result.html, link)
            data["emails"] |= sub_data["emails"]
            data["phones"] |= sub_data["phones"]
            data["linkedin_urls"] |= sub_data["linkedin_urls"]
            data["name_hints"].extend(sub_data["name_hints"])
            if data["emails"] or data["phones"] or data["linkedin_urls"]:
                break

    return json.dumps(
        {
            "url": url,
            "page_title": data["title"],
            "emails": sorted(data["emails"]),
            "phones": sorted(data["phones"]),
            "linkedin_urls": sorted(data["linkedin_urls"]),
            "candidate_name_hints": data["name_hints"][:10],
        }
    )
