"""Tier 2: Crawl4AI, a Playwright-backed crawler that renders JavaScript and
returns cleaned HTML/markdown - handles client-rendered marketing sites the
lighter tiers can't. Import is lazy so the rest of the app still works if the
optional `crawl4ai` dependency isn't installed."""

import asyncio

from config.settings import get_settings
from tools.scraping.base import FetchResult


class Crawl4AIEngine:
    name = "crawl4ai"

    def fetch(self, url: str) -> FetchResult:
        try:
            from crawl4ai import AsyncWebCrawler
        except ImportError as exc:
            return FetchResult(url=url, success=False, engine=self.name, error=f"crawl4ai not installed: {exc}")

        try:
            result = asyncio.run(self._acrawl(AsyncWebCrawler, url))
            html = getattr(result, "html", None) or getattr(result, "cleaned_html", None)
            if not result.success or not html:
                return FetchResult(url=url, success=False, engine=self.name, error=getattr(result, "error_message", "no content"))
            return FetchResult(url=url, success=True, engine=self.name, html=html)
        except Exception as exc:
            # Crawl4AI surfaces Playwright's own errors (e.g. missing browser
            # binaries) as multi-line boxed banners - keep only the first line.
            return FetchResult(url=url, success=False, engine=self.name, error=str(exc).splitlines()[0])

    @staticmethod
    async def _acrawl(crawler_cls, url: str):
        timeout_ms = get_settings().PLAYWRIGHT_TIMEOUT_MS
        async with crawler_cls() as crawler:
            return await crawler.arun(url=url, page_timeout=timeout_ms)
