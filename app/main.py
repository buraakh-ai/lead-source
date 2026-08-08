import logging
import os

from dotenv import load_dotenv

load_dotenv()

_DEBUG_MODE = os.getenv("DEBUG_MODE", "false").strip().lower() in ("1", "true", "yes", "on")

# Stream logs to the console. In debug mode this also surfaces Agno's verbose
# per-agent tool-call/reasoning traces (see debug_mode in agents.py); otherwise
# only INFO-level pipeline progress and above is shown.
logging.basicConfig(
    level=logging.DEBUG if _DEBUG_MODE else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from typing import List  # noqa: E402

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from .pipeline import find_lead_sources, pull_leads, research_business  # noqa: E402
from .schemas import BusinessResearch, LeadSource  # noqa: E402

app = FastAPI(title="AI Lead Generation Pipeline")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Stage 1: Business research ------------------------------------------------
class ResearchBusinessRequest(BaseModel):
    url: str


@app.post("/research-business", response_model=BusinessResearch)
def research_business_endpoint(payload: ResearchBusinessRequest):
    if not payload.url.strip():
        raise HTTPException(status_code=400, detail="url is required")
    try:
        return research_business(payload.url)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# --- Stage 2: Lead sources -----------------------------------------------------
class FindLeadSourcesRequest(BaseModel):
    business_research: BusinessResearch
    source_count: int = Field(default=3, ge=1, le=8)


class LeadSourcesResponse(BaseModel):
    lead_sources: List[LeadSource]


@app.post("/find-lead-sources", response_model=LeadSourcesResponse)
def find_lead_sources_endpoint(payload: FindLeadSourcesRequest):
    try:
        sources = find_lead_sources(payload.business_research, payload.source_count)
        return LeadSourcesResponse(lead_sources=sources)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# --- Stage 3: Pull leads -------------------------------------------------------
class PullLeadsRequest(BaseModel):
    lead_sources: List[LeadSource]
    lead_count: int = Field(default=3, ge=1, le=8)


@app.post("/pull-leads")
def pull_leads_endpoint(payload: PullLeadsRequest):
    try:
        leads = pull_leads(payload.lead_sources, payload.lead_count)
        return {"leads": [lead.model_dump() for lead in leads]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
