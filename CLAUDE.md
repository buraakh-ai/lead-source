# CLAUDE.md

Guidance for Claude Code (or any future session) working in this repository.

## What this is

A multi-agent lead-generation pipeline: given a business website URL, it
researches the business, finds real web pages belonging to that business's
ideal customers, then pulls verified contact details from those pages. Built
on [Agno](https://agno.com), exposed over FastAPI, driven by Streamlit. See
`README.md` for the full architecture diagram and folder-by-folder purpose.

## Layout at a glance

```
agents/        one Agno Agent builder per file
tools/         agent-facing tool functions (fetch, scrape, search, places)
tools/scraping/  multi-engine fetch fallback chain used by the tools above
skills/        Agno SKILL.md-based skills (icp-analysis, contact-extraction)
prompts/       one YAML file per agent - instructions live here, not in Python
orchestration/ per-stage pipeline functions + the Agno Workflow chaining them
llm/           ModelRouter - tier ("low"/"high") -> concrete model
config/        Settings (pydantic-settings) - every env var, incl. all max-attempts/retry caps
backend/       FastAPI app
frontend/      Streamlit app
schemas.py     shared pydantic domain models (BusinessResearch, Lead, ...)
main.py        CLI runner for the whole pipeline, no API/UI needed
docker/        Dockerfiles; docker-compose.yml at repo root wires them together
```

## Conventions specific to this repo

**Prompts live in YAML, not Python.** An agent builder in `agents/*.py` calls
`load_prompt("<name>", **fmt)` (from `prompts/loader.py`) to get its `name`
and `instructions` from `prompts/<name>.yaml`. `{placeholder}` tokens in an
instruction line (e.g. `{source_count}`) are filled in via `.format(**fmt)`.
If you're changing what an agent is told to do, edit the YAML - don't
hardcode instruction strings back into the Python builder.

**Model selection goes through the router, never `os.getenv` directly.**
`llm.router.get_router().agent_kwargs(tier)` returns `model`,
`fallback_config`, `parser_model`, and `debug_mode` for a given
`"low"`/`"high"` tier (see `config.settings.ModelTier`). `"low"` prefers Groq
(open-weight), `"high"` prefers OpenAI (paid); either falls through to the
other cloud provider, then to local Ollama, if the preferred one isn't
configured. Ollama is always the final fallback. Each agent's tier is read
from `Settings` (`BUSINESS_RESEARCH_TIER` / `LEAD_SOURCE_TIER` /
`LEAD_PULLER_TIER`), not hardcoded in the agent builder.

**Skills are Agno's `SKILL.md` mechanism, not ad-hoc helper modules.** A skill
directory needs `SKILL.md` with YAML frontmatter (`name` - lowercase,
hyphenated, must match the directory name - and `description`), and optional
`scripts/`/`references/` subfolders. `agents/skill_registry.py` loads every
skill under `skills/` once via `Skills(loaders=[LocalSkills(path=...)])`.
Attach to an agent with `skills=get_skills()`; the agent then gets
`get_skill_instructions`/`get_skill_reference`/`get_skill_script` tools for
free and must call them explicitly (a skill's instructions text is not
auto-injected into the system prompt beyond a short summary). If you're
tempted to add a new hardcoded block of guidance text to an agent's
instructions, consider whether it belongs in a skill instead.

**Orchestration is Agno's `Workflow`/`Step`, sequential only (no parallel
branches).** `orchestration/lead_pipeline.py` keeps three plain functions
(`research_business`, `find_lead_sources`, `pull_leads`) that the backend's
three separate endpoints call individually (deliberately - this spaces out
LLM calls so per-minute rate limits recover between stages), and also wires
the same three functions into `build_lead_generation_workflow(...)` via
`Step(executor=...)` for single-call sequential execution. A `Step`'s
`executor` function receives a `StepInput` and must return `StepOutput(content=...)`
explicitly - if you just `return` a raw object, Agno stringifies it via `str()`
and downstream steps lose the structured type.

**Every loop/retry cap is a named `Settings` field, not a magic number.**
`LLM_MAX_RETRIES`/`LLM_RETRY_DELAY_SECONDS` (model-level retries before
fallback), `SCRAPER_MAX_ATTEMPTS` (how many scraping engines to try per URL),
`WORKFLOW_STEP_MAX_RETRIES` (Agno Step retries per pipeline stage). If you add
anything that could retry or loop, give it a `Settings` field with a sane
default instead of a bare constant.

**The scraping fallback chain is ordered cheapest-to-heaviest.**
`tools/scraping/fallback_chain.py`'s `_ENGINES` list is `requests` → `Scrapling`
→ `Crawl4AI` → `Playwright`. Each engine's `fetch()` returns a `FetchResult`;
the chain stops at the first result with enough visible text
(`_has_useful_content`, currently 200 chars) to be useful, not just the first
HTTP success - a JS-only page can return a 200 with an empty shell. Engine
imports are lazy (inside `fetch()`) so a missing optional dependency degrades
that one engine to a failure result instead of crashing the app.

## Running / testing

```bash
pip install -r requirements.txt
playwright install chromium

uvicorn backend.main:app --reload      # backend on :8000
streamlit run frontend/streamlit_app.py  # frontend on :8501
python main.py https://example.com     # or run the pipeline once, no server

docker compose up --build              # both, containerized
```

There is no test suite yet. When adding one, prefer testing
`tools/scraping/fallback_chain.py`'s ordering/cap logic and
`tools/contact_extraction.py`'s parsing logic directly (pure functions, no
LLM calls needed) over trying to mock full agent runs.

## Things to watch for

- `.venv` in this repo can drift from `requirements.txt` (e.g. `fastapi` was
  found missing from it during the last restructure) - if an import that
  should obviously exist fails, `pip install -r requirements.txt` first
  before assuming the code is wrong.
- `Workflow`/`Step` import (`agno.workflow`) transitively imports `RemoteWorkflow`,
  which requires `fastapi` to be installed even outside the backend - this is
  fine since `fastapi` is already a hard dependency of the whole project.
- Skill directory names must be lowercase with hyphens only (no underscores) -
  `agno`'s validator rejects `SKILL.md` if `name` doesn't exactly match the
  directory name.
