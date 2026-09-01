"""Persistence into the pre-provisioned ``leadsource`` CRM schema."""

import json
from typing import Any, Optional, Sequence
from urllib.parse import urlparse

from config.settings import get_settings
from schemas import CampaignTarget, Lead, LeadSource, RunSummary

SOURCE_NAME = "AGFINTAX_LEAD_SOURCING"
SHARED_DIRECTORY_DOMAINS = {
    "yellowpages.com",
    "sulekha.com",
    "google.com",
    "maps.google.com",
}


def database_configured() -> bool:
    return bool(get_settings().AWS_POSTGRES_DSN)


def _domain(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    domain = parsed.netloc.lower().removeprefix("www.") or None
    return None if domain in SHARED_DIRECTORY_DOMAINS else domain


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


def _company_identity(record: Lead | LeadSource) -> tuple[str, Optional[str], Optional[str]]:
    if isinstance(record, Lead):
        return (
            record.business_name or record.name,
            _domain(record.website or record.source_url),
            record.google_place_id,
        )
    return record.source_name, _domain(record.url), record.google_place_id


def _find_company_id(
    cursor,
    name: str,
    domain: Optional[str],
    place_id: Optional[str],
    city: Optional[str],
    state: Optional[str],
) -> Optional[int]:
    identity = place_id or domain or f"{name.casefold()}:{(city or '').casefold()}:{(state or '').casefold()}"
    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"company:{identity}",))
    lookups = []
    if place_id:
        lookups.append(("google_place_id = %s", (place_id,)))
    if domain:
        lookups.append(("LOWER(domain) = LOWER(%s)", (domain,)))
    if city and state:
        lookups.append((
            "LOWER(company_name) = LOWER(%s) AND LOWER(COALESCE(city,'')) = LOWER(%s) "
            "AND LOWER(COALESCE(state,'')) = LOWER(%s)",
            (name, city, state),
        ))
    elif city:
        lookups.append((
            "LOWER(company_name) = LOWER(%s) AND LOWER(COALESCE(city,'')) = LOWER(%s)",
            (name, city),
        ))
    else:
        lookups.append(("LOWER(company_name) = LOWER(%s)", (name,)))
    for predicate, values in lookups:
        cursor.execute(
            f"SELECT company_id FROM leadsource.companies WHERE {predicate} ORDER BY company_id LIMIT 1",
            values,
        )
        row = cursor.fetchone()
        if row:
            return row[0]
    return None


def _upsert_company(cursor, record: Lead | LeadSource, campaign: CampaignTarget, summary: RunSummary) -> int:
    name, domain, place_id = _company_identity(record)
    is_lead = isinstance(record, Lead)
    website = (record.website or record.source_url) if is_lead else record.url
    attributes = {
        "campaign_id": campaign.campaign_id,
        "campaign_name": campaign.campaign_name,
        "run_id": summary.run_id,
        "verification_status": record.verification_status,
        "business_status": record.business_status,
        "source_urls": record.source_urls if is_lead else record.evidence_urls,
    }
    values = (
        name, record.category, record.category, website, domain,
        record.phone if is_lead else record.public_phone,
        record.business_email if is_lead else None,
        record.address if is_lead else record.business_address,
        record.city, record.state if is_lead else campaign.state,
        record.country if is_lead else campaign.country, record.rating, record.review_count,
        place_id, _json(attributes), record.model_dump_json(),
    )
    company_id = _find_company_id(
        cursor,
        name,
        domain,
        place_id,
        record.city,
        record.state if is_lead else campaign.state,
    )
    if company_id is None:
        cursor.execute(
            """INSERT INTO leadsource.companies
            (company_name,industry,category,website,domain,phone,email,address,city,state,country,
             rating,review_count,google_place_id,attributes,raw_data)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
            RETURNING company_id""",
            values,
        )
        return cursor.fetchone()[0]
    cursor.execute(
        """UPDATE leadsource.companies SET
        company_name=%s, industry=COALESCE(%s,industry), category=COALESCE(%s,category),
        website=COALESCE(%s,website), domain=COALESCE(%s,domain), phone=COALESCE(%s,phone),
        email=COALESCE(%s,email), address=COALESCE(%s,address), city=COALESCE(%s,city),
        state=COALESCE(%s,state), country=COALESCE(%s,country), rating=COALESCE(%s,rating),
        review_count=COALESCE(%s,review_count), google_place_id=COALESCE(%s,google_place_id),
        attributes=COALESCE(attributes,'{}'::jsonb) || %s::jsonb, raw_data=%s::jsonb,
        updated_at=CURRENT_TIMESTAMP WHERE company_id=%s""",
        (*values, company_id),
    )
    return company_id


def _find_lead_id(cursor, lead: Lead, company_id: int, full_name: str) -> Optional[int]:
    email = lead.personal_email or lead.business_email
    identity = email or (f"{lead.phone}:{company_id}" if lead.phone else f"{full_name.casefold()}:{company_id}")
    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"lead:{identity}",))
    lookups = []
    if email:
        lookups.append(("LOWER(email) = LOWER(%s)", (email,)))
    if lead.phone:
        lookups.append(("phone = %s AND company_id = %s", (lead.phone, company_id)))
    lookups.append(("LOWER(full_name) = LOWER(%s) AND company_id = %s", (full_name, company_id)))
    for predicate, values in lookups:
        cursor.execute(
            f"SELECT lead_id FROM leadsource.leads WHERE {predicate} ORDER BY lead_id LIMIT 1",
            values,
        )
        row = cursor.fetchone()
        if row:
            return row[0]
    return None


def _upsert_lead(cursor, lead: Lead, company_id: int, campaign: CampaignTarget, summary: RunSummary) -> int:
    full_name = lead.decision_maker_name or lead.business_name or lead.name
    lead_type = "PERSON" if lead.decision_maker_name else "BUSINESS"
    attributes = {
        "campaign_id": campaign.campaign_id,
        "campaign_name": campaign.campaign_name,
        "run_id": summary.run_id,
        "verification_status": lead.verification_status,
        "confidence_score": lead.confidence_score,
        "marketing_notes": lead.marketing_notes,
        "source_urls": lead.source_urls,
        "google_maps_url": lead.google_maps_url,
        "business_status": lead.business_status,
    }
    source_url = lead.source_url or (lead.source_urls[0] if lead.source_urls else None)
    verified_at = summary.completed_at if lead.verification_status == "verified" else None
    values = (
        lead_type, "SMALL_BUSINESS" if lead_type == "BUSINESS" else "PROFESSIONAL",
        lead.category, lead.verification_status.upper(), full_name, lead.decision_maker_role,
        lead.decision_maker_role, lead.personal_email or lead.business_email,
        lead.business_email if lead.personal_email else None, lead.phone,
        lead.address, lead.city, lead.state, lead.country, company_id,
        lead.business_name or lead.name, lead.decision_maker_role, SOURCE_NAME, source_url,
        lead.lead_score, _json(attributes), lead.model_dump_json(), summary.completed_at,
        summary.completed_at, verified_at, lead.verification_status == "verified",
    )
    lead_id = _find_lead_id(cursor, lead, company_id, full_name)
    if lead_id is None:
        cursor.execute(
            """INSERT INTO leadsource.leads
            (lead_type,lead_category,lead_subcategory,lead_status,full_name,job_title,profession,
             email,secondary_email,phone,address,city,state,country,company_id,company_name,
             relationship_to_company,source,source_url,lead_score,attributes,raw_data,scraped_at,
             enriched_at,verified_at,is_verified)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s::jsonb,%s::jsonb,%s,%s,%s,%s)
            RETURNING lead_id""",
            values,
        )
        return cursor.fetchone()[0]
    cursor.execute(
        """UPDATE leadsource.leads SET
        lead_type=%s, lead_category=%s, lead_subcategory=COALESCE(%s,lead_subcategory),
        lead_status=%s, full_name=%s, job_title=COALESCE(%s,job_title),
        profession=COALESCE(%s,profession), email=COALESCE(%s,email),
        secondary_email=COALESCE(%s,secondary_email), phone=COALESCE(%s,phone),
        address=COALESCE(%s,address), city=COALESCE(%s,city), state=COALESCE(%s,state),
        country=COALESCE(%s,country), company_id=%s, company_name=%s,
        relationship_to_company=COALESCE(%s,relationship_to_company), source=%s,
        source_url=COALESCE(%s,source_url), lead_score=%s,
        attributes=COALESCE(attributes,'{}'::jsonb) || %s::jsonb, raw_data=%s::jsonb,
        scraped_at=%s, enriched_at=%s, verified_at=COALESCE(%s,verified_at), is_verified=%s,
        updated_at=CURRENT_TIMESTAMP WHERE lead_id=%s""",
        (*values, lead_id),
    )
    return lead_id


def _upsert_social_profile(cursor, lead_id: int, lead: Lead) -> None:
    other_profiles = {"company_linkedin_url": lead.company_linkedin_url} if lead.company_linkedin_url else {}
    if not lead.linkedin_url and not other_profiles:
        return
    cursor.execute(
        "SELECT social_id FROM leadsource.social_profiles WHERE lead_id = %s ORDER BY social_id LIMIT 1",
        (lead_id,),
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            """UPDATE leadsource.social_profiles SET linkedin_url=COALESCE(%s,linkedin_url),
            other_profiles=COALESCE(other_profiles,'{}'::jsonb) || %s::jsonb,
            raw_data=%s::jsonb, updated_at=CURRENT_TIMESTAMP WHERE social_id=%s""",
            (lead.linkedin_url, _json(other_profiles), lead.model_dump_json(), row[0]),
        )
    else:
        cursor.execute(
            """INSERT INTO leadsource.social_profiles (lead_id,linkedin_url,other_profiles,raw_data)
            VALUES (%s,%s,%s::jsonb,%s::jsonb)""",
            (lead_id, lead.linkedin_url, _json(other_profiles), lead.model_dump_json()),
        )


def persist_sourcing_run(
    campaign: CampaignTarget,
    sources: Sequence[LeadSource],
    leads: Sequence[Lead],
    summary: RunSummary,
) -> tuple[bool, str]:
    settings = get_settings()
    if not settings.AWS_POSTGRES_DSN:
        return False, "AWS_POSTGRES_DSN is not configured; results remain available for CSV export."

    import psycopg

    company_ids: dict[tuple[str, Optional[str], Optional[str]], int] = {}
    with psycopg.connect(settings.AWS_POSTGRES_DSN) as connection:
        with connection.cursor() as cursor:
            for source in sources:
                company_ids[_company_identity(source)] = _upsert_company(cursor, source, campaign, summary)
            for lead in leads:
                company_id = _upsert_company(cursor, lead, campaign, summary)
                company_ids[_company_identity(lead)] = company_id
                lead_id = _upsert_lead(cursor, lead, company_id, campaign, summary)
                _upsert_social_profile(cursor, lead_id, lead)
        connection.commit()
    return True, f"Saved {len(company_ids)} companies, {len(leads)} leads, and their social profiles to AWS PostgreSQL."
