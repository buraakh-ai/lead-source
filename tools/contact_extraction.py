"""Shared contact-extraction logic: pulls emails, phone numbers, and LinkedIn
URLs out of a page's HTML using (in order of confidence) schema.org JSON-LD,
the page footer, and - only if both come up empty - a full-page text/link
scan. Used internally by tools/contact_scraper.py, and re-exposed as a
standalone runnable script by the contact-extraction Agno skill
(skills/contact-extraction/scripts/extract_contacts.py) so any agent can
invoke the same logic directly."""

import json
import re
from typing import Any, Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_RE = re.compile(r"(\+?\d[\d\-.\s()]{7,}\d)")


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


_LINK_KEYWORDS = ("about", "contact", "team", "services", "location")


def extract_contacts(html: str, page_url: str) -> dict:
    """Extract contact details and metadata from a page's raw HTML.

    Returns a dict with: title, emails (set), phones (set), linkedin_urls
    (set), name_hints (list), follow_links (list of same-purpose page URLs
    worth following if this page alone has no contact details).
    """
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
