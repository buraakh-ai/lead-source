import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; LeadGenPOC/1.0)"
REQUEST_TIMEOUT = 10

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_RE = re.compile(r"(\+?\d[\d\-.\s()]{7,}\d)")

_LINK_KEYWORDS = ("about", "contact", "team", "services", "location")
_SITEMAP_XML_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _get(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        return None


def fetch_webpage_text(url: str) -> str:
    """
    Fetch a webpage and return its title, meta description, visible text (truncated),
    and links whose text or href suggest they lead to About/Contact/Services pages.

    Args:
        url (str): The webpage URL to fetch.

    Returns:
        str: JSON string with keys: title, meta_description, text, internal_links.
    """
    html = _get(url)
    if not html:
        return json.dumps({"error": f"Could not fetch {url}"})

    soup = BeautifulSoup(html, "html.parser")
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


def google_places_search(query: str, location: str, max_results: int = 6) -> str:
    """
    Search Google Places (Text Search) for small businesses matching a query and location.
    Returns candidate business names/websites/phones found via Google's free-to-use Places
    data - no paid lead aggregators involved.

    Args:
        query (str): What kind of business to search for, e.g. "law firms", "dentists".
        location (str): Geographic location, e.g. "Austin, TX".
        max_results (int): Maximum number of place results to return (capped at 10).

    Returns:
        str: JSON string with a list of {name, website, formatted_address, phone}.
    """
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        return json.dumps({"error": "GOOGLE_PLACES_API_KEY is not configured"})

    max_results = min(max_results, 10)

    try:
        search_resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={"query": f"{query} in {location}", "key": api_key},
            timeout=REQUEST_TIMEOUT,
        )
        search_resp.raise_for_status()
        results = search_resp.json().get("results", [])[:max_results]
    except requests.RequestException as exc:
        return json.dumps({"error": str(exc)})

    places = []
    for r in results:
        place_id = r.get("place_id")
        website = None
        phone = None
        if place_id:
            try:
                detail_resp = requests.get(
                    "https://maps.googleapis.com/maps/api/place/details/json",
                    params={
                        "place_id": place_id,
                        "fields": "website,formatted_phone_number",
                        "key": api_key,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                detail_resp.raise_for_status()
                detail = detail_resp.json().get("result", {})
                website = detail.get("website")
                phone = detail.get("formatted_phone_number")
            except requests.RequestException:
                pass

        places.append(
            {
                "name": r.get("name"),
                "website": website,
                "formatted_address": r.get("formatted_address"),
                "phone": phone,
            }
        )

    return json.dumps({"places": places})


def web_search(query: str, num_results: int = 3) -> str:
    """
    Search Google via SerpAPI and return a COMPACT result list (title, link, and a
    short snippet only). Use this to locate a specific business's contact/about page,
    e.g. 'site:example.com contact' or '"Joe's Diner" Austin contact'.

    Deliberately trims each result to keep token usage low - do not expect full page
    content here; use scrape_contacts on a returned link to actually read a page.

    Args:
        query (str): The Google search query.
        num_results (int): Number of results to return (capped at 5).

    Returns:
        str: JSON string with a list of {title, link, snippet}.
    """
    api_key = os.getenv("SERP_API_KEY")
    if not api_key:
        return json.dumps({"error": "SERP_API_KEY is not configured"})

    num_results = min(num_results, 5)

    try:
        resp = requests.get(
            "https://serpapi.com/search.json",
            params={"q": query, "api_key": api_key, "engine": "google", "num": num_results},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        organic = resp.json().get("organic_results", [])[:num_results]
    except requests.RequestException as exc:
        return json.dumps({"error": str(exc)})

    results = [
        {
            "title": r.get("title"),
            "link": r.get("link"),
            "snippet": (r.get("snippet") or "")[:200],
        }
        for r in organic
    ]
    return json.dumps({"results": results})


def _scan_zone_for_contacts(zone: Any, page_url: str) -> Dict[str, set]:
    """Run mailto/tel/linkedin link extraction plus email/phone regex over one
    subtree (e.g. a <footer>) or a whole page's soup."""
    emails = set()
    phones = set()
    linkedin_urls = set()

    for a in zone.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            emails.add(href.split(":", 1)[1].split("?")[0].strip())
        elif href.lower().startswith("tel:"):
            phones.add(href.split(":", 1)[1].strip())
        elif "linkedin.com" in href.lower():
            linkedin_urls.add(urljoin(page_url, href))

    text = zone.get_text(separator=" ")
    emails.update(EMAIL_RE.findall(text))
    for m in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", m)
        if 7 <= len(digits) <= 15:
            phones.add(m.strip())

    return {"emails": emails, "phones": phones, "linkedin_urls": linkedin_urls}


def _extract_from_jsonld(soup: BeautifulSoup) -> Dict[str, set]:
    """Pull telephone/email out of schema.org JSON-LD (LocalBusiness/Organization/
    ContactPoint blocks), which many sites embed as exact, machine-readable fields
    separate from the visible page text."""
    emails: set = set()
    phones: set = set()

    def harvest(obj: Any) -> None:
        if isinstance(obj, dict):
            email = obj.get("email")
            if isinstance(email, str) and "@" in email:
                emails.add(email.replace("mailto:", "").strip())
            phone = obj.get("telephone")
            if isinstance(phone, str) and phone.strip():
                phones.add(phone.strip())
            for key in ("contactPoint", "@graph"):
                nested = obj.get(key)
                if isinstance(nested, (dict, list)):
                    harvest(nested)
        elif isinstance(obj, list):
            for item in obj:
                harvest(item)

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            harvest(json.loads(raw))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    return {"emails": emails, "phones": phones}


def _find_footer_zones(soup: BeautifulSoup) -> List[Any]:
    zones = list(soup.find_all("footer"))
    seen = {id(z) for z in zones}
    for el in soup.find_all(True):
        if id(el) in seen:
            continue
        el_id = (el.get("id") or "").lower()
        el_class = " ".join(el.get("class") or []).lower()
        if "footer" in el_id or "footer" in el_class:
            zones.append(el)
    return zones


def _extract_contacts(html: str, page_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # Structured data and the footer are extracted before scripts/styles are
    # stripped, since JSON-LD lives inside <script> tags.
    jsonld = _extract_from_jsonld(soup)
    footer_zones = _find_footer_zones(soup)

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    footer = {"emails": set(), "phones": set(), "linkedin_urls": set()}
    for zone in footer_zones:
        zone_contacts = _scan_zone_for_contacts(zone, page_url)
        footer["emails"] |= zone_contacts["emails"]
        footer["phones"] |= zone_contacts["phones"]
        footer["linkedin_urls"] |= zone_contacts["linkedin_urls"]

    # JSON-LD and the footer are high-confidence, targeted sources (structured
    # data, or a site-wide contact block). Only fall back to scanning the whole
    # page's text/links if both come up empty - a broad regex scan over body
    # copy is noisier and more prone to false positives (dates, prices, other
    # people's numbers quoted in blog posts, etc).
    emails = jsonld["emails"] | footer["emails"]
    phones = jsonld["phones"] | footer["phones"]
    linkedin_urls = set(footer["linkedin_urls"])

    if not emails and not phones and not linkedin_urls:
        whole_page = _scan_zone_for_contacts(soup, page_url)
        emails = whole_page["emails"]
        phones = whole_page["phones"]
        linkedin_urls = whole_page["linkedin_urls"]

    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    name_hints = []
    for tag in soup.find_all(["h1", "h2", "h3"]):
        t = tag.get_text(strip=True)
        if t and len(t.split()) <= 6:
            name_hints.append(t)

    follow_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        label = a.get_text(strip=True).lower()
        if any(k in href.lower() or k in label for k in ("contact", "about", "team")):
            follow_links.append(urljoin(page_url, href))

    return {
        "title": title,
        "emails": emails,
        "phones": phones,
        "linkedin_urls": linkedin_urls,
        "name_hints": name_hints[:10],
        "follow_links": list(dict.fromkeys(follow_links))[:5],
    }


def scrape_contacts(url: str) -> str:
    """
    Scrape a webpage for lead contact details: emails and phone numbers from
    schema.org JSON-LD structured data, the page footer (mailto:/tel: links and
    text), and - only if those find nothing - a broader scan of the whole page
    (mailto:/tel: links and page text) plus LinkedIn URLs. If still nothing useful
    is found, follows same-site About/Contact/Team links one level deep.

    Args:
        url (str): The URL of the small business webpage to scrape.

    Returns:
        str: JSON string with keys: url, page_title, emails, phones, linkedin_urls,
             candidate_name_hints (short heading text near contact info, may indicate a
             person's or business's name).
    """
    html = _get(url)
    if not html:
        return json.dumps({"url": url, "error": "Could not fetch page"})

    data = _extract_contacts(html, url)

    if not data["emails"] and not data["phones"] and not data["linkedin_urls"]:
        for link in data["follow_links"]:
            if urlparse(link).netloc != urlparse(url).netloc:
                continue
            sub_html = _get(link)
            if not sub_html:
                continue
            sub_data = _extract_contacts(sub_html, link)
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
