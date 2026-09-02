# Phase 1 Public-Source Lead Sourcing MVP

A configurable, multi-agent Lead Sourcing module built on Agno, FastAPI and
Streamlit. A user defines a time-bound sourcing campaign by country, state,
city/area, industry and decision-maker role. Coordinated agents discover public
business sources, enrich and qualify records, and optionally persist them to a
central AWS PostgreSQL database for the downstream Ad Generator module.

## Documentation

- [Solution Design](docs/SOLUTION_DESIGN.md) — complete product scope,
  features, workflows, components, data, APIs, security, and limitations.
- [Architecture](docs/ARCHITECTURE.md) — system, component, sequence, data, and
  AWS reference diagrams.
- [Product and Operations Guide](docs/PRODUCT_OPERATIONS_GUIDE.md) — setup,
  configuration, usage, deployment, testing, and troubleshooting.
- [Project Change Tracker](docs/CHANGELOG.md) — chronological updates,
  deployment actions, open items, and the template for future changes.

The pipeline runs as three sequential agents (Business Research → Lead Source
Research → Lead Puller), orchestrated with Agno's native `Workflow`/`Step`
primitives, exposed over a FastAPI backend, and driven by a Streamlit
frontend. It's built to run as a container today and grow into an MCP server
later without restructuring.

## Phase 1 capabilities

- Dynamically targets countries, US states, counties, cities, ZIP codes, industries and subcategories.
- Stores a start/end period and stable campaign ID for monthly or occasional sourcing runs.
- Uses Google Places, official business websites, public search results, chambers, and legitimate directories for discovery and corroboration.
- Enriches public business email, phone, decision-maker name/role, company LinkedIn URL, and public professional LinkedIn URL when evidence exists.
- Records supporting source URLs, verification status, confidence, marketing notes, and a deterministic 0-100 lead score.
- Deduplicates by official domain, then phone, then normalized business name and city.
- Displays campaign metrics and exports a UTF-8 CSV from the Streamlit interface.
- Saves and reloads reusable campaign definitions as JSON.
- Optionally persists companies, leads, and social profiles to AWS PostgreSQL.
- Does not infer wealth or other sensitive personal traits and does not bypass Yelp or LinkedIn access controls.

## Architecture

```
                     ┌──────────────────┐
   Streamlit  ──────▶│   FastAPI backend │──────▶ orchestration/lead_pipeline.py
   (frontend/)        │   (backend/)      │        (Agno Workflow, 3 Steps)
                     └──────────────────┘                 │
                                                           ▼
                                          agents/  ──uses──▶  llm/router.py  (model tier routing)
                                            │                 tools/         (Agno tools)
                                            │                 prompts/*.yaml (instructions)
                                            └──uses──▶ skills/  (SKILL.md guidance + scripts)

   tools/scraping/  (fallback chain: requests → Scrapling → Crawl4AI → Playwright)
```

| Folder | Purpose |
|---|---|
| `agents/` | One Agno `Agent` builder per file - Business Research, Lead Source Research, Lead Puller. |
| `tools/` | Agent-facing tool functions (`fetch_webpage_text`, `scrape_contacts`, `discover_contact_pages`, `google_places_search`, `web_search`). |
| `tools/scraping/` | The multi-engine web-scraping fallback chain used internally by the tools above. |
| `skills/` | Agno `SKILL.md`-based skills - reusable guidance/scripts an agent can look up on demand (`icp-analysis`, `contact-extraction`). |
| `prompts/` | One YAML file per agent holding its `instructions` - edit prompt wording here, never in Python. |
| `orchestration/` | The per-stage pipeline functions plus the Agno `Workflow` that chains all three agents sequentially. |
| `llm/` | `ModelRouter` - resolves a "low"/"high" complexity tier to a concrete model + fallback chain. |
| `config/` | Centralized `Settings` (pydantic-settings) - every `.env` knob, including every max-attempts/retry cap. |
| `backend/` | FastAPI app (candidate for a future FastMCP server). |
| `frontend/` | Streamlit UI. |
| `docker/` | Backend/frontend Dockerfiles. |

## How the pieces fit together

**LLM router** (`llm/router.py`): each agent is tagged with a complexity tier -
`"low"` (open-weight model served via Groq) or `"high"` (paid frontier model
via OpenAI) - set per-agent in `.env` (`BUSINESS_RESEARCH_TIER`,
`LEAD_SOURCE_TIER`, `LEAD_PULLER_TIER`; all default to `high`). Whichever
provider isn't configured is skipped automatically, and local Ollama is
always the last-resort offline fallback regardless of tier.

**Scraping fallback chain** (`tools/scraping/`): `fetch_webpage_text` and
`scrape_contacts` fetch pages through `fetch_with_fallback`, which tries
engines cheapest-first and stops at the first one that returns HTML with
enough visible text to be useful:

1. `requests` + BeautifulSoup - works for most static/server-rendered sites.
2. `Scrapling` - stealthy fetcher, gets past basic anti-bot checks.
3. `Crawl4AI` - Playwright-backed, renders JavaScript.
4. `Playwright` (raw) - last resort, full browser control.

`SCRAPER_MAX_ATTEMPTS` (`.env`, default `4`) hard-caps how many engines are
tried per URL, so a bad URL can never cycle through engines indefinitely.

**Skills** (`skills/`): `icp-analysis` holds the heuristics for inferring a
business's ideal customer profile; `contact-extraction` holds the JSON-LD/
footer/regex contact-parsing logic (also used directly by `tools/contact_scraper.py`
for deterministic behavior, and independently runnable via
`skills/contact-extraction/scripts/extract_contacts.py <url>`). Agents access
skills through `get_skill_instructions`/`get_skill_reference`/`get_skill_script`
tools that Agno wires up automatically via `skills=get_skills()`.

**Orchestration** (`orchestration/lead_pipeline.py`): `research_business`,
`find_lead_sources`, and `pull_leads` are plain functions the backend's three
separate endpoints call one at a time (this spacing lets per-minute token
rate limits recover between stages). The same three functions are also wired
into `build_lead_generation_workflow(...)`, an Agno `Workflow` with three
sequential `Step`s, giving a single-call entry point used by the CLI, the
`/run-pipeline` endpoint, and future MCP tool exposure.

## Setup

1. **Python 3.11+**, then:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   playwright install chromium
   ```
2. Copy `.env.example` to `.env` and fill in at least one LLM provider key
   (`GROQ_API_KEY` or `OPENAI_API_KEY`) - or install [Ollama](https://ollama.com)
   and `ollama pull qwen2.5:7b` to run entirely locally/offline.
3. Configure `GOOGLE_PLACES_API_KEY` for local-business discovery and
   `SERP_API_KEY` for public-web fallback searches. Without either service,
   discovery may legitimately return no sources.
4. (Optional) configure AWS PostgreSQL in `.env`:

   ```env
   AWS_POSTGRES_DSN=postgresql://buraq_ai:password@your-rds-host:5432/crmdb?sslmode=require
   ```

   Keep the real credential only in `.env` or AWS Secrets Manager. The backend
   writes to the pre-provisioned `leadsource.companies`, `leadsource.leads`, and
   `leadsource.social_profiles` tables and does not execute DDL.

### Configure the AWS RDS PostgreSQL lead database

For the complete team handoff procedure, including AWS Console, networking,
local initialization, and verification steps, see
[`docs/AWS_RDS_HANDOFF.md`](docs/AWS_RDS_HANDOFF.md).

The client-review preview for deterministic, multi-source discovery is
documented separately in
[`docs/V2_MULTI_SOURCE_DISCOVERY.md`](docs/V2_MULTI_SOURCE_DISCOVERY.md).

1. Use the provisioned `crmdb` database and `leadsource` schema. Allow inbound
   TCP 5432 only from the backend's security group or a temporary administration
   IP; do not expose it to the whole internet.
2. Put the connection string in `.env` locally. In ECS/Lambda, store it in AWS
   Secrets Manager and inject it as `AWS_POSTGRES_DSN`:

   ```env
   AWS_POSTGRES_DSN=postgresql://buraq_ai:URL_ENCODED_PASSWORD@your-instance.region.rds.amazonaws.com:5432/crmdb?sslmode=require
   ```

3. Grant the application user only `CONNECT`, `SELECT`, `INSERT`, and `UPDATE`
   on the three existing tables. No `CREATE` or `DELETE` permission is required.

4. Run a campaign with `persist_to_database: true`. The backend writes companies,
   leads, and social profiles in one transaction.

To verify the handoff with `psql`:

```sql
SELECT lead_id, full_name, email, lead_score
FROM leadsource.leads
ORDER BY created_at DESC
LIMIT 20;
```

## Running locally

```bash
# Backend
uvicorn backend.main:app --reload

# Frontend (separate terminal)
streamlit run frontend/streamlit_app.py

# Or, skip the API/UI entirely and run the pipeline once from the CLI:
python main.py https://example.com --sources 3 --leads 3
```

### Streamlit configuration

Non-secret frontend options and defaults live in
[`frontend/streamlit_config.json`](frontend/streamlit_config.json). To use a
different local file, set `STREAMLIT_CONFIG_FILE` to its path.

For AWS, upload the same JSON structure to an S3 folder and configure the
frontend service with:

```env
STREAMLIT_CONFIG_S3_URI=s3://YOUR_BUCKET/YOUR_FOLDER/streamlit_config.json
```

The frontend workload role needs `s3:GetObject` only for that object. If the S3
object is missing, inaccessible, malformed, or fails validation, the application
shows a warning and uses the bundled defaults. `BACKEND_URL` remains an
environment variable, and credentials or database connection strings must not
be stored in this JSON file.

## Running with Docker

```bash
docker compose up --build
```

This starts the backend on `http://localhost:8000` and the Streamlit frontend
on `http://localhost:8501`, wired together automatically. Only the backend
reads the root `.env` file; the frontend receives `BACKEND_URL` and the optional
non-secret `STREAMLIT_CONFIG_S3_URI`, with AWS credentials supplied by its
workload role when S3 is enabled.

### Run the backend container by itself

The backend and frontend are independent images. The backend image contains
FastAPI, agents, orchestration, scrapers and optional PostgreSQL support; it
does not contain Streamlit. The frontend image contains only Streamlit and its
HTTP client and receives no API keys or database credentials.

```bash
# Build only the backend image
docker compose build backend

# Start only the backend and show its logs
docker compose up backend
```

Verify it at `http://localhost:8000/health`, then open
`http://localhost:8000/docs` and execute `POST /run-sourcing-campaign`.
For a discovery-only smoke test, set `persist_to_database` to `false`. For the
database integration test, leave its default `true`. The API response is
returned to the caller and, while `LOG_SOURCING_DETAILS=true`, each
source and lead is also emitted as structured JSON to stdout. Docker displays
that output directly; Amazon ECS sends it to CloudWatch when the task uses the
`awslogs` log driver.

Use the backend without Compose when testing an image directly:

```bash
docker build -f docker/Dockerfile.backend -t leadscraping0703-backend:latest .
docker run --rm -p 8000:8000 --env-file .env leadscraping0703-backend:latest
```

When PostgreSQL is ready, supply `AWS_POSTGRES_DSN` from AWS Secrets Manager
and send `persist_to_database: true`. Consider setting
`LOG_SOURCING_DETAILS=false` at that point so contact details are retained in
the database rather than CloudWatch logs.

## API

| Endpoint | Purpose |
|---|---|
| `GET /health` | Service and AWS PostgreSQL configuration status |
| `POST /run-sourcing-campaign` | Primary Phase 1 workflow: campaign → sources → qualified leads → optional database handoff |
| `POST /v2/run-sourcing-campaign` | V2 preview: deterministic multi-provider discovery → funnel metrics → batched enrichment → optional database handoff |
| `POST /research-business` | Stage 1: `{url}` → `BusinessResearch` |
| `POST /find-lead-sources` | Stage 2: `{business_research, source_count, campaign_target}` → `{lead_sources}` |
| `POST /pull-leads` | Stage 3: `{lead_sources, lead_count, campaign_target}` → `{leads}` |
| `POST /run-pipeline` | All stages: `{url, source_count, lead_count, campaign_target}` → `{business_research, lead_sources, leads}` |

Example campaign target:

```json
{
  "campaign_id": "generated-uuid",
  "campaign_name": "August Orange County Restaurants",
  "campaign_status": "active",
  "period_start": "2026-08-01",
  "period_end": "2026-08-31",
  "country": "United States",
  "state": "California",
  "geography": "Southern California",
  "cities_or_areas": ["Orange County", "Irvine", "Tustin"],
  "industries": ["restaurants", "retailers"],
  "subcategories": ["independent restaurants", "specialty retailers"],
  "decision_maker_roles": ["Owner", "Founder", "General Manager", "Finance Manager"]
}
```

## Tests

The lead scoring and deduplication tests do not call external APIs:

```bash
python -m unittest discover -s tests -v
```

## Environment variables

See `.env.example` for the full, commented reference (grouped: LLM providers,
LLM router tiers, search/places APIs, scraping fallback chain, orchestration,
frontend, debugging). Every loop/retry-bounding knob (`LLM_MAX_RETRIES`,
`SCRAPER_MAX_ATTEMPTS`, `WORKFLOW_STEP_MAX_RETRIES`) lives in
`config/settings.py`, so "can this ever run forever" always has one place to
check.

## Extending the project

- **New agent**: add `agents/<name>.py` with a `build_<name>_agent()` function
  that calls `get_router().agent_kwargs(tier)` for its model, and add a
  matching `prompts/<name>.yaml` for its instructions.
- **New tool**: add a function to `tools/`, export it from `tools/__init__.py`,
  and add it to the relevant agent's `tools=[...]` list.
- **New skill**: add `skills/<skill-name>/SKILL.md` (name must be lowercase,
  hyphenated, and match the directory name) with optional `scripts/` and
  `references/` subfolders - it's picked up automatically by `get_skills()`.
- **New scraping engine**: implement the `FetchEngine` protocol in
  `tools/scraping/`, then add it to `_ENGINES` in
  `tools/scraping/fallback_chain.py` in cheapest-to-heaviest order.

## Roadmap

- Expose the same tools/agents as an MCP server (FastAPI → FastMCP).
