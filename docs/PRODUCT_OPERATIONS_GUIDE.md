# AGFINTAX Lead Sourcing — Product and Operations Guide

## 1. What the product does

AGFINTAX Lead Sourcing discovers and qualifies public business prospects for a
specific geography and industry. It returns source evidence, contact details,
decision-maker information when publicly supported, quality scores, and a
database handoff for downstream CRM or advertising workflows.

It does not guarantee a requested count, invent missing details, send outreach,
or bypass restricted platforms.

## 2. Quick start

### Prerequisites

- Python 3.11 or 3.12.
- At least one supported LLM setup: OpenAI, Groq, or local Ollama.
- Google Places and/or SerpAPI for useful discovery coverage.
- Chromium installed through Playwright for the full scraper chain.

### Local installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
Copy-Item .env.example .env
```

Set the required values in `.env`, then run:

```powershell
python -m uvicorn backend.main:app --reload
```

In a second terminal:

```powershell
streamlit run frontend/streamlit_app.py
```

Open `http://localhost:8501`. API documentation is available at
`http://localhost:8000/docs`.

### Docker Compose

```powershell
docker compose up --build
```

Frontend: `http://localhost:8501`

Backend health: `http://localhost:8000/health`

## 3. Configure dependencies

### LLM

Configure at least one of:

```env
OPENAI_API_KEY=
GROQ_API_KEY=
OLLAMA_HOST=
```

Agent tiers select the preferred provider:

```env
BUSINESS_RESEARCH_TIER=high
LEAD_SOURCE_TIER=high
LEAD_PULLER_TIER=high
```

`high` prefers OpenAI; `low` prefers Groq. Ollama is the configured fallback.

### Discovery

```env
GOOGLE_PLACES_API_KEY=
SERP_API_KEY=
```

Google Places powers business/place discovery. SerpAPI powers public web,
Yellow Pages-indexed, chamber-indexed, and Sulekha-indexed results.

### PostgreSQL

```env
AWS_POSTGRES_DSN=postgresql://buraq_ai:URL_ENCODED_PASSWORD@HOST:5432/crmdb?sslmode=require
```

The database must already contain the `leadsource.companies`,
`leadsource.leads`, and `leadsource.social_profiles` tables. The application
does not create or alter them.

## 4. Configure Streamlit through JSON/S3

The complete default file is
[`frontend/streamlit_config.json`](../frontend/streamlit_config.json). It
controls page metadata, countries/states/areas, campaign statuses, industries,
roles, providers, result limits, slider defaults, timeouts, and persistence
default behavior.

Do not put secrets, API keys, DSNs, or private customer data in this file.

### Local override

```env
STREAMLIT_CONFIG_FILE=C:\config\streamlit_config.json
```

### AWS S3 override

1. Upload the JSON file to an S3 folder.
2. Grant the frontend workload role `s3:GetObject` on that object.
3. Set:

```env
STREAMLIT_CONFIG_S3_URI=s3://YOUR_BUCKET/YOUR_FOLDER/streamlit_config.json
```

4. Restart the frontend service after changing the S3 object.

S3 takes precedence over a local file. A partial JSON object is allowed and is
merged over defaults. Missing objects, IAM errors, malformed JSON, unknown keys,
wrong types, invalid ranges, or inconsistent selections trigger a visible
warning and the bundled defaults are used.

Example IAM statement:

```json
{
  "Effect": "Allow",
  "Action": "s3:GetObject",
  "Resource": "arn:aws:s3:::YOUR_BUCKET/YOUR_FOLDER/streamlit_config.json"
}
```

## 5. Run a campaign in Streamlit

1. Enter a campaign name and lifecycle status.
2. Choose the period.
3. Select the country, state/region, and cities/counties/ZIP codes.
4. Select industries and optional subcategories.
5. Choose desired decision-maker roles and keyword filters.
6. Select V1 or V2.
7. Set source and lead counts.
8. For V2, choose providers and funnel limits.
9. Confirm whether results should be pushed to PostgreSQL.
10. Select **Run lead sourcing**.

Review:

- **Campaign** for the exact submitted target.
- **Source discovery** for candidate evidence.
- **Qualified leads** for contacts, scores, and CSV download.
- **Database handoff** for run metrics, V2 funnel metrics, and persistence
  status.

Use **Save campaign JSON** to reuse a target. Use **Load campaign JSON** and
**Apply uploaded campaign** to restore it.

## 6. Choose V1 or V2

| Choose | When |
|---|---|
| V1 | Smaller campaigns or when agent-directed tool selection is acceptable. |
| V2 | Coverage, provider control, batching, and measurable funnel behavior matter. |

For a target of 100 qualified leads, a starting V2 source target of 300 and an
oversampling factor of 3 is reasonable, but actual conversion depends on the
market and available public evidence.

## 7. Use the API

### Health

```bash
curl http://localhost:8000/health
```

`database_configured: true` means a DSN exists. It is not a live SQL health
check.

### V2 campaign example

```bash
curl -X POST http://localhost:8000/v2/run-sourcing-campaign \
  -H "Content-Type: application/json" \
  -d '{
    "campaign": {
      "campaign_name": "Irvine Restaurants",
      "campaign_status": "active",
      "country": "United States",
      "state": "California",
      "cities_or_areas": ["Irvine"],
      "industries": ["Restaurants"],
      "decision_maker_roles": ["Owner", "General Manager"]
    },
    "source_count": 30,
    "lead_count": 10,
    "discovery": {
      "providers": ["google_places", "web_search", "chambers"],
      "oversampling_factor": 3,
      "max_queries": 20,
      "results_per_query": 10,
      "max_pages_per_query": 2,
      "enrichment_batch_size": 10
    },
    "persist_to_database": true
  }'
```

## 8. Interpret results

- `sources_discovered`: normalized candidates selected for enrichment.
- `leads_returned`: valid, deduplicated leads after scoring.
- `verified_leads`: leads with email, phone, decision-maker name/role, and
  evidence.
- `enriched_leads`: useful partial leads scoring at least 45.
- `incomplete_leads`: retained results below the enriched threshold.
- `database_saved`: whether the PostgreSQL transaction completed.
- `exhausted_before_target`: providers were exhausted before the raw target.
- `provider_errors`: failed requests grouped by provider.
- `rejection_counts`: missing data, closed businesses, and duplicates.

Fewer leads than requested is valid behavior; review rejections, provider
errors, category/location coverage, and contact availability.

## 9. AWS deployment checklist

### Frontend

- Build with `docker/Dockerfile.frontend`.
- Set `BACKEND_URL` to the reachable backend URL.
- Set `STREAMLIT_CONFIG_S3_URI` if using S3.
- Attach only the required S3 object permission and logging permissions.
- Confirm the S3 region/account policy and any KMS permission if the object uses
  a customer-managed key.

### Backend

- Build `docker/Dockerfile.backend` for a full browser-capable container, or
  `docker/Dockerfile.backend.lambda` for the Lambda-compatible lightweight
  scraper path.
- Inject LLM/search keys and `AWS_POSTGRES_DSN` from Secrets Manager.
- Place backend compute where it can reach private RDS.
- Allow outbound HTTPS to configured providers and public websites.
- Set `LOG_SOURCING_DETAILS=false` when contact data must not enter logs.

### Database

- Database: `crmdb`.
- Schema: `leadsource`.
- Tables: `companies`, `leads`, `social_profiles`.
- User: `buraq_ai` with connect/select/insert/update only.
- Security group: TCP 5432 from backend compute only.

### Post-deployment smoke test

1. Check `/health`.
2. Run a small V2 campaign with 3–5 requested leads.
3. Confirm `database_saved: true`.
4. Query recent rows:

```sql
SELECT lead_id, full_name, email, lead_score, created_at
FROM leadsource.leads
ORDER BY created_at DESC
LIMIT 20;
```

5. Confirm related company and social profile records.
6. Review provider errors, duration, and CloudWatch logs for secrets/contact
   leakage.

## 10. Troubleshooting

| Symptom | Checks |
|---|---|
| S3 configuration warning | Verify URI syntax, object key/case, IAM `s3:GetObject`, region/account policy, KMS access, and JSON validity. Defaults remain active. |
| No sources | Verify Places/SerpAPI keys, selected providers, category/location combinations, quotas, and provider errors. |
| Sources but few leads | Public pages may lack contacts; review source URLs, scraper logs, sitemap results, and enrichment batch counts. |
| LLM rate limits | Reduce campaign size, adjust agent tiers/model IDs, review provider quota, or ensure Ollama fallback is reachable. |
| Thin/JS-only pages | Use the full backend image, confirm Playwright Chromium installation, and review `SCRAPER_MAX_ATTEMPTS`. |
| `database_configured: false` | Inject `AWS_POSTGRES_DSN` into the backend, not the frontend. Restart the backend. |
| `database_saved: false` | Check DSN database name, URL-encoded password, network/security groups, schema/table names, grants, and backend exception type. |
| Duplicate records | Verify stable place IDs/domains/contact values; the DDL has no unique constraints, so non-application writers can still create duplicates. |
| Request timeout | Reduce counts/query limits or move long campaigns to a future queue/worker implementation. |

## 11. Operational controls

- Start with small campaigns to measure cost and conversion.
- Bound V2 with query/page/result controls.
- Monitor API quotas and LLM tokens.
- Rotate secrets without rebuilding images.
- Restart Streamlit to reload S3 configuration.
- Keep database backups and test restore procedures.
- Define retention and deletion policies for lead/contact data.
- Run the test suite before every deployment:

```bash
python -m unittest discover -s tests -v
```

## 12. Release and rollback

1. Record the deployed Git commit and image digest.
2. Deploy to a test environment and complete the smoke test.
3. Promote the same immutable image to production.
4. For application rollback, redeploy the previous image digest.
5. For configuration rollback, restore the previous S3 object version and
   restart the frontend.
6. Database writes are updates/inserts; coordinate any data rollback with the
   data owner rather than deleting records from the application.
