-- Non-production sample records. Run after 001_create_lead_database.sql.
BEGIN;

INSERT INTO lead_sourcing_campaigns
    (campaign_id, campaign_name, campaign_status, period_start, period_end,
     country, state, target_locations, industries, subcategories, configuration)
VALUES
    ('sample-campaign-001', 'Sample Orange County Restaurants', 'active',
     DATE '2026-08-01', DATE '2026-08-31', 'United States', 'California',
     '["Irvine", "Tustin"]'::jsonb, '["restaurants"]'::jsonb,
     '["independent restaurants"]'::jsonb,
     '{"sample": true, "decision_maker_roles": ["Owner", "General Manager"]}'::jsonb)
ON CONFLICT (campaign_id) DO NOTHING;

INSERT INTO lead_sourcing_runs
    (run_id, campaign_id, started_at, completed_at, duration_seconds, metrics)
VALUES
    ('sample-run-001', 'sample-campaign-001', NOW() - INTERVAL '30 seconds', NOW(), 30,
     '{"sources_discovered": 1, "leads_returned": 1, "verified_leads": 1}'::jsonb)
ON CONFLICT (run_id) DO NOTHING;

INSERT INTO lead_sourcing_sources
    (run_id, campaign_id, source_name, source_url, source_type, category, city,
     verification_status, evidence_urls, raw_payload)
SELECT 'sample-run-001', 'sample-campaign-001', 'Sample Bistro',
       'https://example.com/sample-bistro', 'official_website', 'restaurant',
       'Irvine', 'discovered', '["https://example.com/sample-bistro/contact"]'::jsonb,
       '{"sample": true}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM lead_sourcing_sources
    WHERE run_id = 'sample-run-001' AND source_url = 'https://example.com/sample-bistro'
);

INSERT INTO lead_sourcing_leads
    (run_id, campaign_id, business_name, category, website, city, state, country,
     phone, business_email, decision_maker_name, decision_maker_role,
     verification_status, confidence_score, lead_score, marketing_notes,
     source_urls, raw_payload)
SELECT 'sample-run-001', 'sample-campaign-001', 'Sample Bistro', 'restaurant',
       'https://example.com/sample-bistro', 'Irvine', 'California', 'United States',
       '+1-949-555-0100', 'owner@example.com', 'Alex Owner', 'Owner',
       'verified', 95, 90, 'Sample only; replace with generated lead output.',
       '["https://example.com/sample-bistro/contact"]'::jsonb, '{"sample": true}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM lead_sourcing_leads
    WHERE run_id = 'sample-run-001' AND business_name = 'Sample Bistro'
);

COMMIT;
