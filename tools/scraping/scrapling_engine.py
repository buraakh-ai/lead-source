"""Tier 1: Scrapling's static curl_cffi fetcher with browser impersonation.

This remains a lightweight HTTP request rather than a browser-rendering tier.
Import is lazy so the fallback chain can continue when an optional dependency
is missing or broken.
"""

from config.settings import get_settings
from tools.scraping.base import FetchResult


class ScraplingEngine:
    name = "scrapling"

    def fetch(self, url: str) -> FetchResult:
        try:
            from scrapling.fetchers import Fetcher
        except ImportError as exc:
            return FetchResult(url=url, success=False, engine=self.name, error=f"scrapling not installed: {exc}")

        try:
            page = Fetcher.get(
                url,
                impersonate="chrome",
                stealthy_headers=True,
                follow_redirects=True,
                timeout=get_settings().SCRAPER_REQUEST_TIMEOUT_SECONDS,
                retries=1,
            )
            html = getattr(page, "html_content", None) or getattr(page, "body", None)
            status = getattr(page, "status", 200)
            if not html or status >= 400:
                return FetchResult(url=url, success=False, engine=self.name, error=f"status={status}, empty={not html}")
            return FetchResult(url=url, success=True, engine=self.name, html=html)
        except Exception as exc:
            return FetchResult(url=url, success=False, engine=self.name, error=str(exc))
