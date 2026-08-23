-- Run this while connected to the target database as its owner.
-- AWS RDS creates the database itself through the console/CLI; this template
-- creates the application objects inside that database.

BEGIN;

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
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT campaign_period_is_valid CHECK (period_end >= period_start)
);

CREATE TABLE IF NOT EXISTS lead_sourcing_runs (
    run_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES lead_sourcing_campaigns(campaign_id),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    duration_seconds DOUBLE PRECISION NOT NULL CHECK (duration_seconds >= 0),
    metrics JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lead_sourcing_sources (
    source_record_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES lead_sourcing_runs(run_id) ON DELETE CASCADE,
    campaign_id TEXT NOT NULL REFERENCES lead_sourcing_campaigns(campaign_id),
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_type TEXT,
    category TEXT,
    city TEXT,
    verification_status TEXT,
    rating DOUBLE PRECISION CHECK (rating IS NULL OR rating BETWEEN 0 AND 5),
    review_count INTEGER CHECK (review_count IS NULL OR review_count >= 0),
    business_status TEXT,
    evidence_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lead_sourcing_leads (
    lead_record_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES lead_sourcing_runs(run_id) ON DELETE CASCADE,
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
    verification_status TEXT NOT NULL DEFAULT 'incomplete'
        CHECK (verification_status IN ('verified', 'enriched', 'incomplete')),
    confidence_score INTEGER CHECK (confidence_score BETWEEN 0 AND 100),
    lead_score INTEGER CHECK (lead_score BETWEEN 0 AND 100),
    marketing_notes TEXT,
    rating DOUBLE PRECISION CHECK (rating IS NULL OR rating BETWEEN 0 AND 5),
    google_place_id TEXT,
    google_maps_url TEXT,
    review_count INTEGER CHECK (review_count IS NULL OR review_count >= 0),
    business_status TEXT,
    source_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_lead_sourcing_runs_campaign ON lead_sourcing_runs(campaign_id);
CREATE INDEX IF NOT EXISTS ix_lead_sourcing_sources_run ON lead_sourcing_sources(run_id);
CREATE INDEX IF NOT EXISTS ix_lead_sourcing_leads_run ON lead_sourcing_leads(run_id);
CREATE INDEX IF NOT EXISTS ix_lead_sourcing_leads_campaign ON lead_sourcing_leads(campaign_id);
CREATE INDEX IF NOT EXISTS ix_lead_sourcing_leads_business ON lead_sourcing_leads(business_name);
CREATE INDEX IF NOT EXISTS ix_lead_sourcing_leads_email ON lead_sourcing_leads(business_email);

-- Upgrade databases created by an earlier application version.
ALTER TABLE lead_sourcing_leads ADD COLUMN IF NOT EXISTS personal_email TEXT;
ALTER TABLE lead_sourcing_leads ADD COLUMN IF NOT EXISTS google_place_id TEXT;
ALTER TABLE lead_sourcing_leads ADD COLUMN IF NOT EXISTS google_maps_url TEXT;

-- Recreate because PostgreSQL cannot insert/reorder columns via CREATE OR REPLACE VIEW.
DROP VIEW IF EXISTS ad_generator_leads_v;
CREATE VIEW ad_generator_leads_v AS
SELECT l.lead_record_id, l.campaign_id, c.campaign_name, c.period_start, c.period_end,
       l.business_name, l.category, l.website, l.address, l.city, l.state, l.country,
       l.phone, l.business_email, l.personal_email, l.decision_maker_name,
       l.decision_maker_role, l.company_linkedin_url, l.person_linkedin_url,
       l.verification_status, l.confidence_score, l.lead_score, l.marketing_notes,
       l.google_place_id, l.google_maps_url, l.rating, l.review_count,
       l.source_urls, l.created_at
FROM lead_sourcing_leads l
JOIN lead_sourcing_campaigns c ON c.campaign_id = l.campaign_id
WHERE l.verification_status IN ('verified', 'enriched');

COMMIT;
