"""Optional AWS PostgreSQL persistence for Module 1 lead-sourcing output."""

import json
from pathlib import Path
from typing import Sequence

from config.settings import get_settings
from schemas import CampaignTarget, Lead, LeadSource, RunSummary


SCHEMA_PATH = Path(__file__).resolve().parent / "sql" / "001_create_lead_database.sql"
SCHEMA_SQL = SCHEMA_PATH.read_text(encoding="utf-8")


def database_configured() -> bool:
    return bool(get_settings().AWS_POSTGRES_DSN)


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

    with psycopg.connect(settings.AWS_POSTGRES_DSN) as connection:
        with connection.cursor() as cursor:
            if settings.DATABASE_AUTO_CREATE_TABLES:
                cursor.execute(SCHEMA_SQL)
            cursor.execute(
                """
                INSERT INTO lead_sourcing_campaigns (
                    campaign_id, campaign_name, campaign_status, period_start, period_end,
                    country, state, target_locations, industries, subcategories, configuration, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,NOW())
                ON CONFLICT (campaign_id) DO UPDATE SET
                    campaign_name=EXCLUDED.campaign_name,
                    campaign_status=EXCLUDED.campaign_status,
                    period_start=EXCLUDED.period_start,
                    period_end=EXCLUDED.period_end,
                    country=EXCLUDED.country,
                    state=EXCLUDED.state,
                    target_locations=EXCLUDED.target_locations,
                    industries=EXCLUDED.industries,
                    subcategories=EXCLUDED.subcategories,
                    configuration=EXCLUDED.configuration,
                    updated_at=NOW()
                """,
                (campaign.campaign_id, campaign.campaign_name, campaign.campaign_status,
                 campaign.period_start, campaign.period_end, campaign.country, campaign.state,
                 json.dumps(campaign.cities_or_areas), json.dumps(campaign.industries),
                 json.dumps(campaign.subcategories), campaign.model_dump_json()),
            )
            cursor.execute(
                """INSERT INTO lead_sourcing_runs
                (run_id,campaign_id,started_at,completed_at,duration_seconds,metrics)
                VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (run_id) DO UPDATE SET
                    campaign_id=EXCLUDED.campaign_id,
                    started_at=EXCLUDED.started_at,
                    completed_at=EXCLUDED.completed_at,
                    duration_seconds=EXCLUDED.duration_seconds,
                    metrics=EXCLUDED.metrics""",
                (summary.run_id, campaign.campaign_id, summary.started_at, summary.completed_at,
                 summary.duration_seconds, summary.model_dump_json()),
            )
            # A repeated run ID represents a retry of the same atomic handoff.
            cursor.execute("DELETE FROM lead_sourcing_sources WHERE run_id = %s", (summary.run_id,))
            cursor.execute("DELETE FROM lead_sourcing_leads WHERE run_id = %s", (summary.run_id,))
            for source in sources:
                cursor.execute(
                    """INSERT INTO lead_sourcing_sources
                    (run_id,campaign_id,source_name,source_url,source_type,category,city,
                     verification_status,rating,review_count,business_status,evidence_urls,raw_payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
                    (summary.run_id, campaign.campaign_id, source.source_name, source.url,
                     source.source_type, source.category, source.city, source.verification_status,
                     source.rating, source.review_count, source.business_status,
                     json.dumps(source.evidence_urls), source.model_dump_json()),
                )
            for lead in leads:
                cursor.execute(
                    """INSERT INTO lead_sourcing_leads
                    (run_id,campaign_id,business_name,category,website,address,city,state,country,
                     phone,business_email,personal_email,decision_maker_name,decision_maker_role,company_linkedin_url,
                     person_linkedin_url,verification_status,confidence_score,lead_score,marketing_notes,rating,
                     google_place_id,google_maps_url,review_count,business_status,source_urls,raw_payload)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
                    (summary.run_id, campaign.campaign_id, lead.business_name or lead.name,
                     lead.category, lead.website, lead.address, lead.city, lead.state, lead.country,
                     lead.phone, lead.business_email, lead.personal_email, lead.decision_maker_name, lead.decision_maker_role,
                     lead.company_linkedin_url, lead.linkedin_url, lead.verification_status,
                     lead.confidence_score, lead.lead_score, lead.marketing_notes, lead.rating,
                     lead.google_place_id, lead.google_maps_url, lead.review_count,
                     lead.business_status, json.dumps(lead.source_urls),
                     lead.model_dump_json()),
                )
        connection.commit()
    return True, f"Saved {len(leads)} leads and {len(sources)} sources to AWS PostgreSQL."
