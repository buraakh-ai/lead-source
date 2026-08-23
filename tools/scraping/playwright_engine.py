"""Tier 3 (heaviest, last resort): raw Playwright browser control. Used when
neither the static fetchers nor Crawl4AI's higher-level wrapper produce
useful content - e.g. pages needing real user-interaction-like waits.
Import is lazy so the rest of the app still works if the optional
`playwright` dependency (and its browser binaries) isn't installed."""

from config.settings import get_settings
from tools.scraping.base import FetchResult


class PlaywrightEngine:
    name = "playwright"

    def fetch(self, url: str) -> FetchResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            return FetchResult(url=url, success=False, engine=self.name, error=f"playwright not installed: {exc}")

        timeout_ms = get_settings().PLAYWRIGHT_TIMEOUT_MS
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    page = browser.new_page()
                    page.goto(url, timeout=timeout_ms, wait_until="networkidle")
                    html = page.content()
                finally:
                    browser.close()
            return FetchResult(url=url, success=True, engine=self.name, html=html)
        except Exception as exc:
            # Playwright's own errors (e.g. missing browser binaries) come as
            # multi-line boxed banners - keep only the first line.
            return FetchResult(url=url, success=False, engine=self.name, error=str(exc).splitlines()[0])
