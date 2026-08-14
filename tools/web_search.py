import json
import logging

import requests

from config.settings import get_settings

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 10


def web_search(query: str, num_results: int = 3) -> str:
    """
    Search Google through SerpAPI and return a compact result list.

    Use this tool to locate a specific business's Contact or About page,
    for example:
        site:example.com contact
        "Joe's Diner" Austin contact

    Args:
        query: The Google search query.
        num_results: Number of results to return, capped at 5.

    Returns:
        A JSON string containing a list of title, link, and snippet values,
        or an error message when the search fails.
    """
    api_key = get_settings().SERP_API_KEY

    if not api_key:
        logger.error("[Web Search] SERP_API_KEY is not configured")
        return json.dumps({"error": "SERP_API_KEY is not configured"})

    # Keep the value within the supported range.
    num_results = max(1, min(num_results, 5))

    try:
        response = requests.get(
            "https://serpapi.com/search.json",
            params={
                "q": query,
                "api_key": api_key,
                "engine": "google",
                "num": num_results,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()

    except (requests.RequestException, ValueError) as exc:
        logger.exception(
            "[Web Search] request failed: query=%r error=%s",
            query,
            exc,
        )
        return json.dumps({"error": str(exc)})

    # SerpAPI may return HTTP 200 while reporting an API-level error.
    if payload.get("error"):
        error_message = payload["error"]

        logger.error(
            "[Web Search] SerpAPI error: query=%r error=%s",
            query,
            error_message,
        )

        return json.dumps(
            {"error": f"SerpAPI error: {error_message}"}
        )

    organic_results = payload.get("organic_results", [])[:num_results]

    results = [
        {
            "title": result.get("title"),
            "link": result.get("link"),
            "snippet": (result.get("snippet") or "")[:200],
        }
        for result in organic_results
        if result.get("link")
    ]

    logger.info(
        "[Web Search] query=%r returned=%d",
        query,
        len(results),
    )

    return json.dumps({"results": results})