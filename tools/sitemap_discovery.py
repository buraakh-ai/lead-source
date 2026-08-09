import json
import xml.etree.ElementTree as ET
from typing import List, Optional
from urllib.parse import urlparse

import requests

from config.settings import get_settings

USER_AGENT = "Mozilla/5.0 (compatible; LeadGenPOC/1.0)"
_LINK_KEYWORDS = ("about", "contact", "team", "services", "location")
_SITEMAP_XML_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _get(url: str) -> Optional[str]:
    # Sitemaps/robots.txt are static XML/text, never JS-rendered, so a plain
    # GET (not the heavier multi-engine scraping fallback chain) is enough.
    try:
        timeout = get_settings().SCRAPER_REQUEST_TIMEOUT_SECONDS
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        return None


def _parse_sitemap_locs(xml_text: str) -> List[str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    def locs(parent_tag: str) -> List[str]:
        entries = root.findall(f"sm:{parent_tag}", _SITEMAP_XML_NS) or root.findall(parent_tag)
        found = []
        for entry in entries:
            loc = entry.find("sm:loc", _SITEMAP_XML_NS)
            if loc is None:
                loc = entry.find("loc")
            if loc is not None and loc.text:
                found.append(loc.text.strip())
        return found

    if root.tag.lower().endswith("sitemapindex"):
        return locs("sitemap")
    return locs("url")


def discover_contact_pages(url: str) -> str:
    """
    Discover candidate About/Contact/Team page URLs for a website via its XML
    sitemap (sitemap.xml, or a sitemap path listed in robots.txt), instead of
    relying on links visible in the page's own navigation. Free - no search API
    calls used. Useful when a page's nav doesn't surface a direct contact page,
    or as a first choice before falling back to a paid-search-budget tool.

    Args:
        url (str): Any page URL on the target website (its domain root is used).

    Returns:
        str: JSON string with keys: sitemap_found (bool), candidate_urls (list of
             page URLs whose path suggests About/Contact/Team/Location content).
    """
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    sitemap_urls = [f"{base}/sitemap.xml"]
    robots_txt = _get(f"{base}/robots.txt")
    if robots_txt:
        for line in robots_txt.splitlines():
            if line.strip().lower().startswith("sitemap:"):
                sitemap_urls.append(line.split(":", 1)[1].strip())

    sitemap_found = False
    page_urls: List[str] = []

    for sitemap_url in dict.fromkeys(sitemap_urls):
        xml_text = _get(sitemap_url)
        if not xml_text:
            continue
        sitemap_found = True

        entries = _parse_sitemap_locs(xml_text)
        sub_sitemaps = [e for e in entries if e.lower().endswith(".xml")][:3]
        page_urls.extend(e for e in entries if not e.lower().endswith(".xml"))

        for sub_url in sub_sitemaps:
            sub_xml = _get(sub_url)
            if sub_xml:
                page_urls.extend(_parse_sitemap_locs(sub_xml))

        if page_urls:
            break

    candidates = [u for u in dict.fromkeys(page_urls) if any(k in u.lower() for k in _LINK_KEYWORDS)]

    return json.dumps({"sitemap_found": sitemap_found, "candidate_urls": candidates[:8]})
