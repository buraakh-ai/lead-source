import re
from typing import Optional
from urllib.parse import urlparse

from schemas import Lead


def _normalise(value: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _lead_key(lead: Lead) -> str:
    website = lead.website or lead.source_url or (lead.source_urls[0] if lead.source_urls else None)
    if website:
        domain = urlparse(website).netloc.lower().removeprefix("www.")
        if domain:
            return f"domain:{domain}"
    if lead.phone:
        return f"phone:{_normalise(lead.phone)}"
    return f"name:{_normalise(lead.business_name or lead.name)}:{_normalise(lead.city)}"


def score_and_deduplicate_leads(leads: list[Lead]) -> list[Lead]:
    """Score campaign completeness and retain the best record per business."""
    best_by_key: dict[str, Lead] = {}
    for lead in leads:
        evidence = list(dict.fromkeys([u for u in [*lead.source_urls, lead.source_url] if u]))
        lead.source_urls = evidence
        score = 0
        score += 25 if lead.business_email else 0
        score += 20 if lead.phone else 0
        score += 20 if lead.decision_maker_name else 0
        score += 10 if lead.decision_maker_role else 0
        score += 10 if (lead.linkedin_url or lead.company_linkedin_url) else 0
        score += 10 if lead.website else 0
        score += 5 if evidence else 0
        lead.lead_score = min(score, 100)
        lead.confidence_score = max(lead.confidence_score, min(100, 35 + 15 * min(len(evidence), 3)))
        complete = bool(lead.business_email and lead.phone and lead.decision_maker_name and lead.decision_maker_role)
        lead.verification_status = "verified" if complete and evidence else "enriched" if score >= 45 else "incomplete"
        key = _lead_key(lead)
        if key not in best_by_key or lead.lead_score > best_by_key[key].lead_score:
            best_by_key[key] = lead
    return sorted(best_by_key.values(), key=lambda item: item.lead_score, reverse=True)
