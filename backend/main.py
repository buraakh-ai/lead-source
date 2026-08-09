import logging
from typing import List

from config.settings import get_settings

_settings = get_settings()

# Stream logs to the console. In debug mode this also surfaces Agno's verbose
# per-agent tool-call/reasoning traces (see debug_mode in llm/router.py), otherwise
# only INFO-level pipeline progress and above is shown.
logging.basicConfig(
    level=logging.DEBUG if _settings.DEBUG_MODE else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from orchestration.lead_pipeline import (  # noqa: E402
    build_lead_generation_workflow,
    find_lead_sources,
    pull_leads,
    research_business,
)
from schemas import BusinessResearch, Lead, LeadSource  # noqa: E402

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


# --- Convenience: run the full sequential workflow in one call -----------------
class RunPipelineRequest(BaseModel):
    url: str
    source_count: int = Field(default=3, ge=1, le=8)
    lead_count: int = Field(default=3, ge=1, le=8)


class RunPipelineResponse(BaseModel):
    business_research: BusinessResearch
    lead_sources: List[LeadSource]
    leads: List[Lead]


@app.post("/run-pipeline", response_model=RunPipelineResponse)
def run_pipeline_endpoint(payload: RunPipelineRequest):
    """Runs all three agents sequentially as a single Agno Workflow, instead
    of the frontend driving each stage over three separate calls. Useful for
    scripted/API callers (and the future MCP tool surface)."""
    if not payload.url.strip():
        raise HTTPException(status_code=400, detail="url is required")
    try:
        workflow = build_lead_generation_workflow(payload.source_count, payload.lead_count)
        run_output = workflow.run(input=payload.url)

        step_outputs = run_output.step_results or []
        business_research = step_outputs[0].content
        lead_sources = step_outputs[1].content
        leads = step_outputs[2].content

        return RunPipelineResponse(
            business_research=business_research,
            lead_sources=lead_sources,
            leads=leads,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
