import json
import logging

import requests

from config.settings import get_settings

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT = 10


def google_places_search(
    query: str,
    location: str,
    max_results: int = 6,
) -> str:
    """
    Search Google Places for businesses matching a query and location.

    Returns:
        A JSON string containing business names, websites,
        addresses, and phone numbers.
    """
    api_key = get_settings().GOOGLE_PLACES_API_KEY

    if not api_key:
        logger.error("[Google Places] GOOGLE_PLACES_API_KEY is not configured")
        return json.dumps(
            {"error": "GOOGLE_PLACES_API_KEY is not configured"}
        )

    max_results = min(max_results, 10)

    try:
        search_resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={
                "query": f"{query} in {location}",
                "key": api_key,
            },
            timeout=REQUEST_TIMEOUT,
        )
        search_resp.raise_for_status()
        payload = search_resp.json()

        logger.info(
            "[Google Places] query=%r location=%r status=%s error=%s",
            query,
            location,
            payload.get("status"),
            payload.get("error_message"),
        )

    except (requests.RequestException, ValueError) as exc:
        logger.exception(
            "[Google Places] search failed: query=%r location=%r error=%s",
            query,
            location,
            exc,
        )
        return json.dumps({"error": str(exc)})

    status = payload.get("status", "UNKNOWN_ERROR")

    if status not in ("OK", "ZERO_RESULTS"):
        error_message = payload.get("error_message", "no details")

        logger.error(
            "[Google Places] API error: status=%s message=%s",
            status,
            error_message,
        )

        return json.dumps(
            {
                "error": (
                    f"Google Places API error ({status}): "
                    f"{error_message}"
                )
            }
        )

    results = payload.get("results", [])[:max_results]
    places = []

    for result in results:
        place_id = result.get("place_id")
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

                detail_payload = detail_resp.json()
                detail_status = detail_payload.get("status", "UNKNOWN_ERROR")

                if detail_status == "OK":
                    detail = detail_payload.get("result", {})
                    website = detail.get("website")
                    phone = detail.get("formatted_phone_number")
                else:
                    logger.warning(
                        "[Google Places] details failed: "
                        "place_id=%s status=%s error=%s",
                        place_id,
                        detail_status,
                        detail_payload.get("error_message"),
                    )

            except (requests.RequestException, ValueError) as exc:
                logger.warning(
                    "[Google Places] details request failed: "
                    "place_id=%s error=%s",
                    place_id,
                    exc,
                )

        places.append(
            {
                "name": result.get("name"),
                "website": website,
                "formatted_address": result.get("formatted_address"),
                "phone": phone,
            }
        )

    logger.info(
        "[Google Places] returned=%d websites=%d",
        len(places),
        sum(1 for place in places if place.get("website")),
    )

    return json.dumps({"places": places})