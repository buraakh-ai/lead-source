"""Runs the fetch engines in a fixed cheapest-to-heaviest order, stopping at
the first one that returns HTML with enough visible text to be useful.
Bounded by SCRAPER_MAX_ATTEMPTS so a bad URL can never cycle through engines
indefinitely."""

from typing import List

from agno.utils.log import log_warning
from bs4 import BeautifulSoup

from config.settings import get_settings
from tools.scraping.base import FetchEngine, FetchResult
from tools.scraping.crawl4ai_engine import Crawl4AIEngine
from tools.scraping.playwright_engine import PlaywrightEngine
from tools.scraping.requests_engine import RequestsEngine
from tools.scraping.scrapling_engine import ScraplingEngine

# Deliberately low: real small-business pages almost always clear this easily,
# it just needs to catch near-empty JS-shell pages (e.g. a bare <div id="root">)
# where a heavier rendering engine is actually worth trying.
_MIN_USEFUL_TEXT_CHARS = 120

# Cheapest/most-likely-to-work first; heaviest (real browser) last.
_ENGINES: List[FetchEngine] = [
    RequestsEngine(),
    ScraplingEngine(),
    Crawl4AIEngine(),
    PlaywrightEngine(),
]


def _has_useful_content(html: str) -> bool:
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
    return len(text) >= _MIN_USEFUL_TEXT_CHARS


def fetch_with_fallback(url: str) -> FetchResult:
    max_attempts = max(1, get_settings().SCRAPER_MAX_ATTEMPTS)
    engines = _ENGINES[:max_attempts]

    last_result = FetchResult(url=url, success=False, engine="none", error="no engines configured")
    for engine in engines:
        try:
            result = engine.fetch(url)
        except Exception as exc:  # an engine's optional dependency may be missing/misconfigured
            result = FetchResult(url=url, success=False, engine=engine.name, error=str(exc))

        last_result = result
        if result.success and result.html and _has_useful_content(result.html):
            return result
        log_warning(
            f"[scraping] {engine.name} did not yield useful content for {url}: "
            f"{result.error or 'thin content'}"
        )

    return last_result
