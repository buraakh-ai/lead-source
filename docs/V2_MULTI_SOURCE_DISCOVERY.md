# Version 2: Multi-Source Discovery Preview

Version 2 is available on `main` alongside Version 1. Operators can select the
pipeline version in Streamlit or call the V2 endpoint directly.

## Objective

Version 1 asks an LLM agent to decide which discovery tools to call. A request
for 100 is therefore an upper bound, and may yield far fewer candidates.
Version 2 makes candidate discovery deterministic and measurable:

```text
Campaign targeting
  -> category x location x provider query plan
  -> paginated provider adapters
  -> raw candidate validation
  -> cross-provider deduplication
  -> bounded enrichment batches
  -> global lead scoring/deduplication
  -> CSV and optional PostgreSQL handoff
```

## Providers

- `google_places`: Google Places Text Search and Place Details, including
  `next_page_token` pagination.
- `web_search`: general public business/contact results through SerpAPI.
- `yellow_pages`: indexed Yellow Pages results through a domain-scoped SerpAPI
  query.
- `chambers`: indexed chamber-of-commerce directory results through SerpAPI.
- `sulekha`: indexed Sulekha results through a domain-scoped SerpAPI query.

Directory adapters use public search indexes. They do not bypass logins,
CAPTCHAs, robots controls, or directory access restrictions. Before production,
the client should approve each provider and replace search-index adapters with
official APIs or licensed feeds where commercially required.

## Why the funnel can still return fewer leads

Version 2 improves discovery coverage; it does not fabricate a guaranteed lead
count. Candidates are rejected when they have no name or URL, represent a closed
business, duplicate another provider's record, or do not yield a public phone,
email, or LinkedIn URL during enrichment.

The response reports:

- planned and executed queries;
- raw, unique, and selected candidate counts;
- accepted candidates by provider;
- rejection counts and provider errors;
- enrichment batches and sources attempted;
- final verified, enriched, and incomplete lead counts.

For 100 qualified leads, begin with 300 raw candidates using an oversampling
factor of 3, then tune the factor from observed conversion rates.

## API

Use `POST /v2/run-sourcing-campaign`. Example discovery configuration:

```json
{
  "campaign": {
    "campaign_name": "Orange County Restaurants V2",
    "campaign_status": "draft",
    "country": "United States",
    "state": "California",
    "cities_or_areas": ["Irvine", "Tustin", "Anaheim"],
    "industries": ["Restaurants"],
    "subcategories": ["Independent restaurants"]
  },
  "source_count": 300,
  "lead_count": 100,
  "discovery": {
    "providers": ["google_places", "web_search", "yellow_pages", "chambers"],
    "oversampling_factor": 3,
    "max_queries": 40,
    "results_per_query": 10,
    "max_pages_per_query": 2,
    "enrichment_batch_size": 10
  },
  "persist_to_database": true
}
```

The Streamlit sidebar exposes the same options under **Version 2 preview**.
Database persistence defaults to enabled. For local or preview-only runs, either
leave `AWS_POSTGRES_DSN` unset (persistence is skipped safely) or explicitly send
`persist_to_database: false`.

## Configuration and cost controls

Google Places requires `GOOGLE_PLACES_API_KEY`; the other current adapters
require `SERP_API_KEY`. Provider requests and LLM enrichment may incur charges.
Use `max_queries`, `results_per_query`, `max_pages_per_query`, and
`enrichment_batch_size` to bound request volume.

## Approval checklist

1. Confirm allowed providers, regions, and directory licensing requirements.
2. Validate candidate relevance and duplicate rates for representative markets.
3. Measure cost and duration for 25, 50, and 100 qualified-lead targets.
4. Review contact-data retention, logging, and deletion requirements.
5. Approve the V2 funnel metrics and UI.
6. Promote V2 usage after representative AWS/RDS, quality, and cost testing.
