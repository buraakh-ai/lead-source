import logging
from typing import List

from config.settings import get_settings

_settings = get_settings()
logger = logging.getLogger("lead_sourcing.api")

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
    run_sourcing_campaign,
)
from database import database_configured, persist_sourcing_run  # noqa: E402
from schemas import (  # noqa: E402
    BusinessResearch,
    CampaignTarget,
    Lead,
    LeadSource,
    SourcingCampaignResponse,
)

app = FastAPI(title="AI Lead Generation Pipeline")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def service_endpoint():
    return {
        "service": "AGFINTAX Lead Sourcing Backend",
        "status": "ready",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/health")
def health_endpoint():
    return {
        "status": "ok",
        "module": "lead-sourcing",
        "database_configured": database_configured(),
    }


class SourcingCampaignRequest(BaseModel):
    campaign: CampaignTarget
    source_count: int = Field(default=10, ge=1, le=50)
    lead_count: int = Field(default=10, ge=1, le=50)
    persist_to_database: bool = True


@app.post("/run-sourcing-campaign", response_model=SourcingCampaignResponse)
def run_sourcing_campaign_endpoint(payload: SourcingCampaignRequest):
    if not payload.campaign.industries and not payload.campaign.subcategories:
        raise HTTPException(status_code=400, detail="At least one industry or subcategory is required")
    if not payload.campaign.state and not payload.campaign.cities_or_areas:
        raise HTTPException(status_code=400, detail="A state or city/area is required")
    try:
        logger.info(
            "campaign_started campaign_id=%s name=%r location=%r industries=%s source_count=%d lead_count=%d persist=%s",
            payload.campaign.campaign_id,
            payload.campaign.campaign_name,
            payload.campaign.location_label(),
            payload.campaign.industries or payload.campaign.subcategories,
            payload.source_count,
            payload.lead_count,
            payload.persist_to_database,
        )
        sources, leads, summary = run_sourcing_campaign(
            payload.campaign, payload.source_count, payload.lead_count
        )
        summary.database_configured = database_configured()
        if payload.persist_to_database:
            try:
                saved, message = persist_sourcing_run(payload.campaign, sources, leads, summary)
                summary.database_saved = saved
                summary.database_message = message
            except Exception as database_exc:
                logging.exception("AWS PostgreSQL persistence failed")
                summary.database_saved = False
                summary.database_message = (
                    "Lead discovery succeeded, but AWS PostgreSQL persistence failed: "
                    f"{type(database_exc).__name__}. CSV export remains available."
                )
        response = SourcingCampaignResponse(
            campaign=payload.campaign,
            lead_sources=sources,
            leads=leads,
            run_summary=summary,
        )
        logger.info(
            "campaign_completed run_id=%s campaign_id=%s sources=%d leads=%d verified=%d enriched=%d database_saved=%s",
            summary.run_id,
            summary.campaign_id,
            summary.sources_discovered,
            summary.leads_returned,
            summary.verified_leads,
            summary.enriched_leads,
            summary.database_saved,
        )
        if _settings.LOG_SOURCING_DETAILS:
            for source in sources:
                logger.info("sourcing_source=%s", source.model_dump_json())
            for lead in leads:
                logger.info("sourcing_lead=%s", lead.model_dump_json())
        return response
    except Exception as exc:
        logger.exception("campaign_failed campaign_id=%s", payload.campaign.campaign_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
    source_count: int = Field(default=8, ge=1, le=20)
    campaign_target: CampaignTarget = Field(default_factory=CampaignTarget)


class LeadSourcesResponse(BaseModel):
    lead_sources: List[LeadSource]


@app.post("/find-lead-sources", response_model=LeadSourcesResponse)
def find_lead_sources_endpoint(payload: FindLeadSourcesRequest):
    try:
        sources = find_lead_sources(payload.business_research, payload.source_count, payload.campaign_target)
        return LeadSourcesResponse(lead_sources=sources)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# --- Stage 3: Pull leads -------------------------------------------------------
class PullLeadsRequest(BaseModel):
    lead_sources: List[LeadSource]
    lead_count: int = Field(default=8, ge=1, le=20)
    campaign_target: CampaignTarget = Field(default_factory=CampaignTarget)


@app.post("/pull-leads")
def pull_leads_endpoint(payload: PullLeadsRequest):
    try:
        leads = pull_leads(payload.lead_sources, payload.lead_count, payload.campaign_target)
        return {"leads": [lead.model_dump() for lead in leads]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# --- Convenience: run the full sequential workflow in one call -----------------
class RunPipelineRequest(BaseModel):
    url: str
    source_count: int = Field(default=8, ge=1, le=20)
    lead_count: int = Field(default=8, ge=1, le=20)
    campaign_target: CampaignTarget = Field(default_factory=CampaignTarget)


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
        workflow = build_lead_generation_workflow(
            payload.source_count, payload.lead_count, payload.campaign_target
        )
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
