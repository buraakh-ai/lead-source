# LeadScraping0703

A prototype AI-powered lead generation pipeline built with FastAPI and Agno agents.

The project uses a three-stage pipeline to:
1. Research a target business from its website.
2. Discover candidate lead source pages for the business's ICP.
3. Scrape contact details for valid leads.

## Overview

The API is implemented in `app/main.py` and exposes three endpoints:
- `POST /research-business` — analyze a business website and return its name, location, services, ICP, and search categories.
- `POST /find-lead-sources` — find candidate source pages for leads based on the business research.
- `POST /pull-leads` — scrape contact details from lead source pages and return validated leads.

The pipeline functions are in `app/pipeline.py`, and the agent configuration is defined in `app/agents.py`.

## Requirements

- Python 3.14+
- Dependencies listed in `requirements.txt`

## Installation

1. Create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Create a `.env` file at the repository root with any required API keys.

## Environment Variables

The project supports the following environment variables:

- `DEBUG_MODE` — enable verbose logging when set to `1`, `true`, `yes`, or `on`.
- `GROQ_API_KEY` — use Groq as the primary model.
- `GROQ_MODEL_ID` — optional Groq model ID (default: `llama-3.3-70b-versatile`).
- `OPENAI_API_KEY` — use OpenAI as the primary model.
- `OPENAI_MODEL_ID` — optional OpenAI model ID (default: `gpt-4o`).
- `OLLAMA_HOST` — host URL for Ollama.
- `OLLAMA_MODEL_ID` — optional Ollama model ID (default: `qwen2.5:7b`).
- `GOOGLE_PLACES_API_KEY` — required for `google_places_search`.
- `SERP_API_KEY` — required for `web_search`.

### Model selection behavior

- If `GROQ_API_KEY` is configured, Groq is used as the primary model.
- Else if `OPENAI_API_KEY` is configured, OpenAI is used.
- Otherwise, the local Ollama model is used as a fallback.
- If a cloud model is configured, Ollama is also used as a fallback for rate limits or failures.

## Running the API

Start the FastAPI server from the repository root:

```powershell
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

## API Endpoints

### `POST /research-business`

Request body:

```json
{
  "url": "https://example.com"
}
```

Response model: `app.schemas.BusinessResearch`

Fields include:
- `business_name`
- `location`
- `services`
- `icp`
- `icp_categories`
- `branding_notes`

### `POST /find-lead-sources`

Request body:

```json
{
  "business_research": { /* BusinessResearch object */ },
  "source_count": 3
}
```

Response model:

```json
{
  "lead_sources": [ /* list of LeadSource objects */ ]
}
```

Each `LeadSource` includes:
- `source_name`
- `url`
- `why_relevant`
- `stitching_instructions`

### `POST /pull-leads`

Request body:

```json
{
  "lead_sources": [ /* list of LeadSource objects */ ],
  "lead_count": 3
}
```

Response body:

```json
{
  "leads": [ /* list of Lead objects */ ]
}
```

Each `Lead` includes:
- `name`
- `phone`
- `business_email`
- `personal_email`
- `linkedin_url`
- `source_url`

## Agent Behavior

### Business Research Agent
Defined in `app/agents.py` via `build_business_research_agent()`.
- Reads a business homepage and up to 2 internal About/Services/Contact pages.
- Extracts business name, location, services, branding, and ICP categories.
- Returns structured output using `app.schemas.BusinessResearch`.

### Lead Source Research Agent
Defined in `app/agents.py` via `build_lead_source_agent(source_count)`.
- Uses `google_places_search`, `discover_contact_pages`, and `web_search`.
- Finds candidate web pages for businesses in the target's ICP categories.
- Avoids competitors by never returning businesses in the same category as the target.
- Returns structured output using `app.schemas.LeadSourceList`.

### Lead Puller Agent
Defined in `app/agents.py` via `build_lead_puller_agent(lead_count)`.
- Scrapes contact details from candidate source pages using `scrape_contacts`.
- May follow `discover_contact_pages` if needed to reach an actual contact page.
- Validates leads by requiring a name plus at least one phone/email/LinkedIn URL.
- Returns structured output using `app.schemas.LeadList`.

## Tools and Helpers

The helper functions in `app/tools.py` include:
- `fetch_webpage_text(url)` — fetch page text, title, meta description, and candidate links.
- `google_places_search(query, location, max_results)` — query Google Places and return business websites.
- `web_search(query, num_results)` — query Google Search via SerpAPI.
- `scrape_contacts(url)` — extract contact emails, phone numbers, and LinkedIn URLs.
- `discover_contact_pages(url)` — find likely contact/about pages using sitemap and link heuristics.

## Notes

- `app/pipeline.py` orchestrates the three-stage flow, exposing each stage separately for frontend integration.
- The project currently uses simple `logging` and environment-based debug mode.
- `app/main.py` contains a standalone print entrypoint used only when running the module directly.

## License

This repository does not include a license file. Add one if you intend to publish or share the code.
