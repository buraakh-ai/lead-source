-- Team reference: one shared AWS RDS PostgreSQL destination.
-- Run manually in the intended database. Matches config/aws_output.example.json.
-- Standalone: do not run 001_create_lead_database.sql or 002_sample_data.sql for this design.
-- Intentionally fails if public.leads already exists; review existing DDL first.
BEGIN;

CREATE TABLE public.leads (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    business_name TEXT,
    category TEXT NOT NULL DEFAULT 'individual',
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    comment TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    webinar_id TEXT,
    file_name TEXT,
    CONSTRAINT leads_category_check CHECK (category IN ('business', 'individual')),
    CONSTRAINT leads_business_names_check CHECK (
        category <> 'business' OR (first_name IS NULL AND last_name IS NULL)
    )
);

CREATE INDEX leads_source_lookup_idx ON public.leads (source_name, source_id);
CREATE INDEX leads_loaded_at_idx ON public.leads (loaded_at);

COMMENT ON TABLE public.leads IS
    'Shared append-only ingestion destination for leadsource, Zoom, Bitrix and other producers; no automatic entity deduplication.';
COMMENT ON COLUMN public.leads.id IS
    'Destination-generated row identity across all sources; producers omit this column.';
COMMENT ON COLUMN public.leads.source_id IS
    'Producer-supplied identifier or source category code; not unique. leadsource currently uses lead:0 and lead:1.';
COMMENT ON COLUMN public.leads.category IS
    'Entity kind, not industry. Legacy person imports may omit this column and default to individual.';
COMMENT ON COLUMN public.leads.comment IS
    'Plain text from other producers or serialized JSON with full lead/campaign details from leadsource.';
COMMENT ON COLUMN public.leads.loaded_at IS
    'Ingestion timestamp; producers should supply an explicit timezone offset or use the database default.';

COMMIT;
