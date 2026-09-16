-- Illustrative data only, not scraped records. Run after shared_destination_schema.sql.
-- This transaction ROLLS BACK: rows are displayed but not retained.
-- Identity sequence numbers may still be consumed.
BEGIN;

INSERT INTO public.leads
    (business_name, category, source_id, source_name, source_type,
     first_name, last_name, email, phone, comment, webinar_id, file_name)
VALUES
    (NULL, 'individual', 'zoom:0', 'zoom', 'webinar_registration',
     'Vijay', 'Reddi', 'vijay@example.com', '+1-202-555-0100',
     'Email from AG FinTax', '123456', 'zoom Data.csv'),
    (NULL, 'individual', 'bitrix:0', 'bitrix', 'contact',
     'Arno', 'Gita', 'arno@example.com', '+1-202-555-0101',
     'Caller requested a callback', NULL, NULL),
    ('Demo Restaurant', 'business', 'lead:0', 'leadsource', 'web_scraping',
     NULL, NULL, 'business@example.com', '+1-202-555-0102',
     '{"lead":{"name":"Demo Restaurant","category":"Restaurant"},"run_id":"illustrative-demo"}',
     NULL, NULL),
    (NULL, 'individual', 'lead:1', 'leadsource', 'web_scraping',
     'Hari', 'Pandey', 'hari@example.com', '+1-202-555-0103',
     '{"lead":{"name":"Hari Pandey","category":"individual"},"run_id":"illustrative-demo"}',
     NULL, NULL)
RETURNING *;

ROLLBACK;
