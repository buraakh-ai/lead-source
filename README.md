# AI Lead Generation Pipeline

A modular, multi-agent lead-generation pipeline built on [Agno](https://agno.com):
given a business's website, it researches the business, finds real web pages
belonging to that business's ideal customers, and pulls verified contact
details (name + phone/email/LinkedIn) from those pages.

The pipeline runs as three sequential agents (Business Research → Lead Source
Research → Lead Puller), orchestrated with Agno's native `Workflow`/`Step`
primitives, exposed over a FastAPI backend, and driven by a Streamlit
frontend. It's built to run as a container today and grow into an MCP server
later without restructuring.

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
3. (Optional) `SERP_API_KEY` and `GOOGLE_PLACES_API_KEY` improve lead-source
   discovery; the pipeline still runs without them.

## Running locally

```bash
# Backend
uvicorn backend.main:app --reload

# Frontend (separate terminal)
streamlit run frontend/streamlit_app.py

# Or, skip the API/UI entirely and run the pipeline once from the CLI:
python main.py https://example.com --sources 3 --leads 3
```

## Running with Docker

```bash
docker compose up --build
```

This starts the backend on `http://localhost:8000` and the Streamlit frontend
on `http://localhost:8501`, wired together automatically. Both containers
read the same root `.env` file.

## API

| Endpoint | Purpose |
|---|---|
| `POST /research-business` | Stage 1: `{url}` → `BusinessResearch` |
| `POST /find-lead-sources` | Stage 2: `{business_research, source_count}` → `{lead_sources}` |
| `POST /pull-leads` | Stage 3: `{lead_sources, lead_count}` → `{leads}` |
| `POST /run-pipeline` | All three stages in one call via the Agno Workflow: `{url, source_count, lead_count}` → `{business_research, lead_sources, leads}` |

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
