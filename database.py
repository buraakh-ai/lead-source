"""Optional AWS PostgreSQL persistence for Module 1 lead-sourcing output."""

import json
from typing import Sequence

from config.settings import get_settings
from schemas import CampaignTarget, Lead, LeadSource, RunSummary


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS lead_sourcing_campaigns (
    campaign_id TEXT PRIMARY KEY,
    campaign_name TEXT NOT NULL,
    campaign_status TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    country TEXT,
    state TEXT,
    target_locations JSONB NOT NULL DEFAULT '[]'::jsonb,
    industries JSONB NOT NULL DEFAULT '[]'::jsonb,
    subcategories JSONB NOT NULL DEFAULT '[]'::jsonb,
    configuration JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lead_sourcing_runs (
    run_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES lead_sourcing_campaigns(campaign_id),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    duration_seconds DOUBLE PRECISION NOT NULL,
    metrics JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lead_sourcing_sources (
    source_record_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES lead_sourcing_runs(run_id),
    campaign_id TEXT NOT NULL REFERENCES lead_sourcing_campaigns(campaign_id),
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_type TEXT,
    category TEXT,
    city TEXT,
    verification_status TEXT,
    rating DOUBLE PRECISION,
    review_count INTEGER,
    business_status TEXT,
    evidence_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lead_sourcing_leads (
    lead_record_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES lead_sourcing_runs(run_id),
    campaign_id TEXT NOT NULL REFERENCES lead_sourcing_campaigns(campaign_id),
    business_name TEXT NOT NULL,
    category TEXT,
    website TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    phone TEXT,
    business_email TEXT,
    personal_email TEXT,
    decision_maker_name TEXT,
    decision_maker_role TEXT,
    company_linkedin_url TEXT,
    person_linkedin_url TEXT,
    verification_status TEXT,
    confidence_score INTEGER,
    lead_score INTEGER,
    marketing_notes TEXT,
    google_place_id TEXT,
    google_maps_url TEXT,
    rating DOUBLE PRECISION,
    review_count INTEGER,
    business_status TEXT,
    source_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_lead_sourcing_leads_campaign ON lead_sourcing_leads(campaign_id);
CREATE INDEX IF NOT EXISTS ix_lead_sourcing_leads_business ON lead_sourcing_leads(business_name);
CREATE INDEX IF NOT EXISTS ix_lead_sourcing_leads_email ON lead_sourcing_leads(business_email);
CREATE INDEX IF NOT EXISTS ix_lead_sourcing_leads_run ON lead_sourcing_leads(run_id);
CREATE INDEX IF NOT EXISTS ix_lead_sourcing_sources_run ON lead_sourcing_sources(run_id);

-- Safe upgrades for databases created by an earlier application version.
ALTER TABLE lead_sourcing_leads ADD COLUMN IF NOT EXISTS personal_email TEXT;
ALTER TABLE lead_sourcing_leads ADD COLUMN IF NOT EXISTS google_place_id TEXT;
ALTER TABLE lead_sourcing_leads ADD COLUMN IF NOT EXISTS google_maps_url TEXT;

DROP VIEW IF EXISTS ad_generator_leads_v;
CREATE VIEW ad_generator_leads_v AS
SELECT
    l.lead_record_id,
    l.campaign_id,
    c.campaign_name,
    c.period_start,
    c.period_end,
    l.business_name,
    l.category,
    l.website,
    l.address,
    l.city,
    l.state,
    l.country,
    l.phone,
    l.business_email,
    l.personal_email,
    l.decision_maker_name,
    l.decision_maker_role,
    l.company_linkedin_url,
    l.person_linkedin_url,
    l.verification_status,
    l.confidence_score,
    l.lead_score,
    l.marketing_notes,
    l.google_place_id,
    l.google_maps_url,
    l.rating,
    l.review_count,
    l.source_urls,
    l.created_at
FROM lead_sourcing_leads l
JOIN lead_sourcing_campaigns c ON c.campaign_id = l.campaign_id
WHERE l.verification_status IN ('verified', 'enriched');
"""


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
                VALUES (%s,%s,%s,%s,%s,%s::jsonb)""",
                (summary.run_id, campaign.campaign_id, summary.started_at, summary.completed_at,
                 summary.duration_seconds, summary.model_dump_json()),
            )
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
