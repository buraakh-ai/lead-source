"""Deterministic, multi-provider candidate discovery for the V2 pipeline."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import logging
import time
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import requests

from config.settings import get_settings
from schemas import CampaignTarget, DiscoveryMetrics, DiscoveryOptions, LeadSource
from tools.google_places import google_places_error

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 10


@dataclass(frozen=True)
class DiscoveryQuery:
    provider: str
    category: str
    location: str


@dataclass
class Candidate:
    provider: str
    name: str
    url: str
    category: str
    city: str
    address: Optional[str] = None
    phone: Optional[str] = None
    place_id: Optional[str] = None
    maps_url: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    business_status: Optional[str] = None
    business_types: list[str] | None = None
    evidence_urls: list[str] | None = None


PageCursor = str | int | None
ProviderFetcher = Callable[
    [DiscoveryQuery, PageCursor, int],
    tuple[list[Candidate], PageCursor, Optional[str]],
]


DIRECTORY_DOMAINS = {
    "yellow_pages": "yellowpages.com",
    "sulekha": "sulekha.com",
}


def build_discovery_plan(
    campaign: CampaignTarget,
    options: DiscoveryOptions,
) -> list[DiscoveryQuery]:
    categories = list(dict.fromkeys(campaign.industries + campaign.subcategories))
    locations = campaign.cities_or_areas or [campaign.state or campaign.country]
    queries = [
        DiscoveryQuery(provider=provider, category=category, location=location)
        for location in locations
        for category in categories
        for provider in dict.fromkeys(options.providers)
    ]
    return queries[: options.max_queries]


def _google_places_fetch(
    query: DiscoveryQuery,
    cursor: PageCursor,
    page_size: int,
) -> tuple[list[Candidate], PageCursor, Optional[str]]:
    api_key = get_settings().GOOGLE_PLACES_API_KEY
    if not api_key:
        return [], None, "GOOGLE_PLACES_API_KEY is not configured"

    params = {"query": f"{query.category} in {query.location}", "key": api_key}
    if isinstance(cursor, str):
        # Google documents a short activation delay for next_page_token.
        time.sleep(2)
        params = {"pagetoken": cursor, "key": api_key}
    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return [], None, str(exc)
    if payload.get("status") not in ("OK", "ZERO_RESULTS"):
        status = payload.get("status", "Places error")
        return [], None, google_places_error(status, payload.get("error_message"))

    candidates: list[Candidate] = []
    for item in payload.get("results", [])[:page_size]:
        place_id = item.get("place_id")
        details: dict[str, Any] = {}
        if place_id:
            try:
                detail_response = requests.get(
                    "https://maps.googleapis.com/maps/api/place/details/json",
                    params={
                        "place_id": place_id,
                        "fields": "name,website,formatted_phone_number,url,business_status,types",
                        "key": api_key,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                detail_response.raise_for_status()
                detail_payload = detail_response.json()
                if detail_payload.get("status") == "OK":
                    details = detail_payload.get("result", {})
            except (requests.RequestException, ValueError):
                logger.warning("V2 Places detail lookup failed for %s", place_id)
        url = details.get("website") or details.get("url")
        candidates.append(
            Candidate(
                provider=query.provider,
                name=item.get("name") or details.get("name") or "",
                url=url or "",
                category=query.category,
                city=query.location,
                address=item.get("formatted_address"),
                phone=details.get("formatted_phone_number"),
                place_id=place_id,
                maps_url=details.get("url"),
                rating=item.get("rating"),
                review_count=item.get("user_ratings_total"),
                business_status=item.get("business_status") or details.get("business_status"),
                business_types=item.get("types") or details.get("types") or [],
                evidence_urls=[value for value in (details.get("url"), url) if value],
            )
        )
    return candidates, payload.get("next_page_token"), None


def _serp_fetch(
    query: DiscoveryQuery,
    cursor: PageCursor,
    page_size: int,
) -> tuple[list[Candidate], PageCursor, Optional[str]]:
    api_key = get_settings().SERP_API_KEY
    if not api_key:
        return [], None, "SERP_API_KEY is not configured"
    page = int(cursor or 0)

    if query.provider in DIRECTORY_DOMAINS:
        search_query = f'site:{DIRECTORY_DOMAINS[query.provider]} "{query.category}" "{query.location}"'
    elif query.provider == "chambers":
        search_query = f'"{query.category}" "{query.location}" chamber of commerce directory'
    else:
        search_query = f'"{query.category}" "{query.location}" business contact'
    try:
        response = requests.get(
            "https://serpapi.com/search.json",
            params={
                "q": search_query,
                "api_key": api_key,
                "engine": "google",
                "num": page_size,
                "start": page * page_size,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return [], None, str(exc)
    if payload.get("error"):
        return [], None, str(payload["error"])

    results = payload.get("organic_results", [])[:page_size]
    candidates = [
        Candidate(
            provider=query.provider,
            name=item.get("title") or "",
            url=item.get("link") or "",
            category=query.category,
            city=query.location,
            evidence_urls=[item["link"]] if item.get("link") else [],
        )
        for item in results
    ]
    next_page = page + 1 if len(results) == page_size else None
    return candidates, next_page, None


def _candidate_key(candidate: Candidate) -> str:
    if candidate.place_id:
        return f"place:{candidate.place_id}"
    host = urlparse(candidate.url).netloc.lower().removeprefix("www.")
    is_directory = candidate.provider in {*DIRECTORY_DOMAINS, "chambers"}
    if host and not is_directory and host != "google.com" and not host.endswith("google.com"):
        return f"domain:{host}"
    normalized = "".join(ch for ch in candidate.name.lower() if ch.isalnum())
    location = "".join(ch for ch in candidate.city.lower() if ch.isalnum())
    return f"name:{normalized}:{location}"


def _to_source(candidate: Candidate, campaign_id: str) -> LeadSource:
    provider_label = candidate.provider.replace("_", " ")
    return LeadSource(
        campaign_id=campaign_id,
        source_name=candidate.name,
        url=candidate.url,
        why_relevant=f"Found by {provider_label} for {candidate.category} in {candidate.city}.",
        source_type=candidate.provider,
        category=candidate.category,
        business_address=candidate.address,
        city=candidate.city,
        public_phone=candidate.phone,
        google_place_id=candidate.place_id,
        google_maps_url=candidate.maps_url,
        rating=candidate.rating,
        review_count=candidate.review_count,
        business_status=candidate.business_status,
        business_types=candidate.business_types or [],
        evidence_urls=candidate.evidence_urls or [candidate.url],
        verification_status="discovered",
        stitching_instructions=(
            "Use this public directory result to locate and verify the official business website."
            if candidate.provider in {*DIRECTORY_DOMAINS, "chambers"}
            else "Inspect the official Contact or About page for contact details."
        ),
    )


def discover_sources_v2(
    campaign: CampaignTarget,
    source_count: int,
    lead_count: int,
    options: DiscoveryOptions,
    provider_fetchers: Optional[dict[str, ProviderFetcher]] = None,
) -> tuple[list[LeadSource], DiscoveryMetrics]:
    plan = build_discovery_plan(campaign, options)
    target = min(1000, max(source_count, lead_count) * options.oversampling_factor)
    metrics = DiscoveryMetrics(
        requested_sources=source_count,
        requested_leads=lead_count,
        raw_candidate_target=target,
        queries_planned=len(plan),
    )
    fetchers = provider_fetchers or {
        "google_places": _google_places_fetch,
        "web_search": _serp_fetch,
        "yellow_pages": _serp_fetch,
        "chambers": _serp_fetch,
        "sulekha": _serp_fetch,
    }
    accepted: dict[str, Candidate] = {}
    provider_counts: Counter[str] = Counter()
    rejected: Counter[str] = Counter()
    errors: Counter[str] = Counter()

    for query in plan:
        fetcher = fetchers.get(query.provider)
        if not fetcher:
            rejected["unsupported_provider"] += 1
            continue
        cursor: PageCursor = None
        for _ in range(options.max_pages_per_query):
            candidates, next_cursor, error = fetcher(query, cursor, options.results_per_query)
            metrics.queries_executed += 1
            if error:
                errors[query.provider] += 1
                logger.warning(
                    "V2 provider request failed provider=%s category=%r location=%r error=%s",
                    query.provider,
                    query.category,
                    query.location,
                    error,
                )
                break
            metrics.raw_candidates += len(candidates)
            for candidate in candidates:
                if not candidate.name.strip():
                    rejected["missing_name"] += 1
                    continue
                if not candidate.url.strip():
                    rejected["missing_url"] += 1
                    continue
                if (candidate.business_status or "").upper() in {"CLOSED_PERMANENTLY", "CLOSED"}:
                    rejected["closed_business"] += 1
                    continue
                key = _candidate_key(candidate)
                if key in accepted:
                    rejected["duplicate"] += 1
                    continue
                accepted[key] = candidate
                provider_counts[candidate.provider] += 1
            if len(accepted) >= target or next_cursor is None:
                break
            cursor = next_cursor
        if len(accepted) >= target:
            break

    sources = [_to_source(candidate, campaign.campaign_id) for candidate in accepted.values()]
    sources = sources[:source_count]
    metrics.unique_candidates = len(accepted)
    metrics.sources_selected = len(sources)
    metrics.provider_counts = dict(provider_counts)
    metrics.rejection_counts = dict(rejected)
    metrics.provider_errors = dict(errors)
    metrics.exhausted_before_target = len(accepted) < target
    return sources, metrics
