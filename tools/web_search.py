import json

import requests

from config.settings import get_settings

REQUEST_TIMEOUT = 10


def web_search(query: str, num_results: int = 3) -> str:
    """
    Search Google via SerpAPI and return a COMPACT result list (title, link, and a
    short snippet only). Use this to locate a specific business's contact/about page,
    e.g. 'site:example.com contact' or '"Joe's Diner" Austin contact'.

    Deliberately trims each result to keep token usage low - do not expect full page
    content here; use scrape_contacts on a returned link to actually read a page.

    Args:
        query (str): The Google search query.
        num_results (int): Number of results to return (capped at 5).

    Returns:
        str: JSON string with a list of {title, link, snippet}.
    """
    api_key = get_settings().SERP_API_KEY
    if not api_key:
        return json.dumps({"error": "SERP_API_KEY is not configured"})

    num_results = min(num_results, 5)

    try:
        resp = requests.get(
            "https://serpapi.com/search.json",
            params={"q": query, "api_key": api_key, "engine": "google", "num": num_results},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        organic = resp.json().get("organic_results", [])[:num_results]
    except requests.RequestException as exc:
        return json.dumps({"error": str(exc)})

    results = [
        {
            "title": r.get("title"),
            "link": r.get("link"),
            "snippet": (r.get("snippet") or "")[:200],
        }
        for r in organic
    ]
    return json.dumps({"results": results})
