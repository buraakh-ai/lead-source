#!/usr/bin/env python
"""Standalone runner for the contact-extraction skill: fetches a URL and
prints extracted contact details as JSON. The extraction logic itself lives
in tools/contact_extraction.py (shared with tools/contact_scraper.py) - this
script just adds the repo root to sys.path and exposes it as a skill script
that any agent can invoke via get_skill_script(execute=True).

Usage: python extract_contacts.py <url>
"""

import json
import sys
from pathlib import Path

# Walk up from skills/contact-extraction/scripts/ to the repo root so
# `tools.contact_extraction` is importable regardless of the script's cwd.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import requests  # noqa: E402

from tools.contact_extraction import extract_contacts  # noqa: E402

USER_AGENT = "Mozilla/5.0 (compatible; LeadGenPOC/1.0)"


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"error": "usage: extract_contacts.py <url>"}))
        return 1

    url = sys.argv[1]
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(json.dumps({"error": f"Could not fetch {url}: {exc}"}))
        return 1

    data = extract_contacts(resp.text, url)
    print(
        json.dumps(
            {
                "url": url,
                "title": data["title"],
                "emails": sorted(data["emails"]),
                "phones": sorted(data["phones"]),
                "linkedin_urls": sorted(data["linkedin_urls"]),
                "name_hints": data["name_hints"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
