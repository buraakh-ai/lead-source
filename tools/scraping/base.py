from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class FetchResult:
    """Outcome of a single fetch engine's attempt to load a URL."""

    url: str
    success: bool
    engine: str
    html: Optional[str] = None
    error: Optional[str] = None


class FetchEngine(Protocol):
    """One way of fetching a URL's rendered HTML. Each tier in the fallback
    chain (tools/scraping/fallback_chain.py) implements this."""

    name: str

    def fetch(self, url: str) -> FetchResult: ...
