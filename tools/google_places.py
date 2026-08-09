import json

import requests

from config.settings import get_settings

REQUEST_TIMEOUT = 10


def google_places_search(query: str, location: str, max_results: int = 6) -> str:
    """
    Search Google Places (Text Search) for small businesses matching a query and location.
    Returns candidate business names/websites/phones found via Google's free-to-use Places
    data - no paid lead aggregators involved.

    Args:
        query (str): What kind of business to search for, e.g. "law firms", "dentists".
        location (str): Geographic location, e.g. "Austin, TX".
        max_results (int): Maximum number of place results to return (capped at 10).

    Returns:
        str: JSON string with a list of {name, website, formatted_address, phone}.
    """
    api_key = get_settings().GOOGLE_PLACES_API_KEY
    if not api_key:
        return json.dumps({"error": "GOOGLE_PLACES_API_KEY is not configured"})

    max_results = min(max_results, 10)

    try:
        search_resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={"query": f"{query} in {location}", "key": api_key},
            timeout=REQUEST_TIMEOUT,
        )
        search_resp.raise_for_status()
        payload = search_resp.json()
    except requests.RequestException as exc:
        return json.dumps({"error": str(exc)})

    # Google Places returns HTTP 200 even on failure (bad key, quota, disabled
    # API) - the real outcome is in "status". Only "OK"/"ZERO_RESULTS" mean
    # the request itself succeeded; anything else is a config problem that
    # would otherwise look like "no businesses found" to the agent.
    status = payload.get("status", "UNKNOWN_ERROR")
    if status not in ("OK", "ZERO_RESULTS"):
        return json.dumps({"error": f"Google Places API error ({status}): {payload.get('error_message', 'no details')}"})

    results = payload.get("results", [])[:max_results]

    places = []
    for r in results:
        place_id = r.get("place_id")
        website = None
        phone = None
        if place_id:
            try:
                detail_resp = requests.get(
                    "https://maps.googleapis.com/maps/api/place/details/json",
                    params={
                        "place_id": place_id,
                        "fields": "website,formatted_phone_number",
                        "key": api_key,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                detail_resp.raise_for_status()
                detail = detail_resp.json().get("result", {})
                website = detail.get("website")
                phone = detail.get("formatted_phone_number")
            except requests.RequestException:
                pass

        places.append(
            {
                "name": r.get("name"),
                "website": website,
                "formatted_address": r.get("formatted_address"),
                "phone": phone,
            }
        )

    return json.dumps({"places": places})
