"""Tier 0 (cheapest): a plain HTTP GET. Works for the large majority of small
business marketing sites, which are static/server-rendered. No JS execution,
so it fails (deliberately, by returning success=False) on client-rendered
pages, letting the fallback chain move on to a heavier engine."""

import requests

from config.settings import get_settings
from tools.scraping.base import FetchResult

USER_AGENT = "Mozilla/5.0 (compatible; LeadGenPOC/1.0)"


class RequestsEngine:
    name = "requests"

    def fetch(self, url: str) -> FetchResult:
        timeout = get_settings().SCRAPER_REQUEST_TIMEOUT_SECONDS
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            resp.raise_for_status()
            return FetchResult(url=url, success=True, engine=self.name, html=resp.text)
        except requests.RequestException as exc:
            return FetchResult(url=url, success=False, engine=self.name, error=str(exc))
