"""Tier 1: Scrapling's stealthy fetcher - still a plain HTTP fetch (no full
browser), but with fingerprint/header spoofing to get past basic anti-bot
checks that reject the plain `requests` engine. Import is lazy so the rest of
the app still works if the optional `scrapling` dependency isn't installed."""

from tools.scraping.base import FetchResult


class ScraplingEngine:
    name = "scrapling"

    def fetch(self, url: str) -> FetchResult:
        try:
            from scrapling.fetchers import StealthyFetcher
        except ImportError as exc:
            return FetchResult(url=url, success=False, engine=self.name, error=f"scrapling not installed: {exc}")

        try:
            page = StealthyFetcher.fetch(url)
            html = getattr(page, "html_content", None) or getattr(page, "body", None)
            status = getattr(page, "status", 200)
            if not html or status >= 400:
                return FetchResult(url=url, success=False, engine=self.name, error=f"status={status}, empty={not html}")
            return FetchResult(url=url, success=True, engine=self.name, html=html)
        except Exception as exc:
            return FetchResult(url=url, success=False, engine=self.name, error=str(exc))
