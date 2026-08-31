from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from agno.utils.log import log_info
from agno.workflow import Step, StepInput, StepOutput, Workflow

from agents import build_business_research_agent, build_lead_puller_agent, build_lead_source_agent
from config.settings import get_settings
from lead_quality import score_and_deduplicate_leads
from schemas import (
    BusinessResearch,
    CampaignTarget,
    Lead,
    LeadList,
    LeadSource,
    LeadSourceList,
    RunSummary,
    DiscoveryMetrics,
    DiscoveryOptions,
)
from orchestration.discovery_v2 import discover_sources_v2

# Each stage is exposed as its own function (and its own FastAPI endpoint), so the
# three agents don't have to run back-to-back inside a single request. The frontend
# calls them sequentially and renders each result as it arrives, which also gives
# the per-minute token rate-limit window time to recover between stages.
#
# The same three functions are also wired into an Agno Workflow below
# (build_lead_generation_workflow) for true sequential multi-agent orchestration
# in a single call - used by the CLI, the /run-pipeline endpoint, and (later) an
# MCP tool.


def research_business(url: str) -> BusinessResearch:
    """Stage 1: understand the target business from its URL."""
    log_info(f"[Pipeline] Stage 1/3: researching business at {url}")
    agent = build_business_research_agent()
    result: BusinessResearch = agent.run(input=url).content
    log_info(
        f"[Pipeline] Business research done: {result.business_name} "
        f"({result.location}); icp_categories={result.icp_categories}"
    )
    return result


def find_lead_sources(
    business_research: BusinessResearch,
    source_count: int,
    campaign_target: Optional[CampaignTarget] = None,
) -> List[LeadSource]:
    """Stage 2: find candidate lead-source web pages for the business's ICP."""
    log_info(f"[Pipeline] Stage 2/3: researching {source_count} lead sources")
    agent = build_lead_source_agent(source_count)
    target = campaign_target or CampaignTarget()
    agent_input = (
        f"Target business research:\n{business_research.model_dump_json(indent=2)}\n\n"
        f"Campaign target:\n{target.model_dump_json(indent=2)}\n\n"
        f"Find up to {source_count} qualified business source pages."
    )
    result: LeadSourceList = agent.run(input=agent_input).content
    sources = result.sources[:source_count]
    log_info(f"[Pipeline] Lead source research done: found {len(sources)} sources")
    return sources


def pull_leads(
    lead_sources: List[LeadSource],
    lead_count: int,
    campaign_target: Optional[CampaignTarget] = None,
) -> List[Lead]:
    """Stage 3: pull and validate lead contact details from the source pages."""
    log_info(f"[Pipeline] Stage 3/3: pulling up to {lead_count} leads from {len(lead_sources)} sources")
    agent = build_lead_puller_agent(lead_count)
    target = campaign_target or CampaignTarget()
    agent_input = (
        "Lead source pages to pull from:\n"
        f"{LeadSourceList(sources=lead_sources).model_dump_json(indent=2)}\n\n"
        f"Campaign target:\n{target.model_dump_json(indent=2)}\n\n"
        f"Pull at most {lead_count} leads."
    )
    result: LeadList = agent.run(input=agent_input).content

    valid_leads = [
        lead
        for lead in result.leads
        if lead.name
        and (
            lead.phone
            or lead.business_email
            or lead.personal_email
            or lead.linkedin_url
            or lead.company_linkedin_url
        )
    ]
    leads = score_and_deduplicate_leads(valid_leads)[:lead_count]
    for lead in leads:
        lead.campaign_id = target.campaign_id
        lead.campaign_name = target.campaign_name
        lead.state = lead.state or target.state
        lead.country = lead.country or target.country
    log_info(f"[Pipeline] Lead pulling done: {len(leads)} valid leads out of {len(result.leads)} returned")
    return leads


def run_sourcing_campaign(
    campaign_target: CampaignTarget,
    source_count: int,
    lead_count: int,
) -> tuple[List[LeadSource], List[Lead], RunSummary]:
    """Primary Phase 1 workflow: campaign config -> sources -> qualified leads."""
    started_at = datetime.now(timezone.utc)
    run_id = str(uuid4())
    profile = BusinessResearch(
        business_name="Lead Sourcing Client",
        location=campaign_target.location_label(),
        services=["Prospect discovery and qualification"],
        icp=(
            f"Businesses in {campaign_target.location_label()} matching "
            f"{', '.join(campaign_target.industries + campaign_target.subcategories)}."
        ),
        icp_categories=campaign_target.industries + campaign_target.subcategories,
        branding_notes="Campaign-defined public-source lead sourcing profile.",
    )
    sources = find_lead_sources(profile, source_count, campaign_target)
    for source in sources:
        source.campaign_id = campaign_target.campaign_id
    leads = pull_leads(sources, lead_count, campaign_target)
    for lead in leads:
        lead.run_id = run_id
    completed_at = datetime.now(timezone.utc)
    summary = RunSummary(
        run_id=run_id,
        campaign_id=campaign_target.campaign_id,
        campaign_name=campaign_target.campaign_name,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=round((completed_at - started_at).total_seconds(), 3),
        sources_discovered=len(sources),
        leads_returned=len(leads),
        verified_leads=sum(lead.verification_status == "verified" for lead in leads),
        enriched_leads=sum(lead.verification_status == "enriched" for lead in leads),
        incomplete_leads=sum(lead.verification_status == "incomplete" for lead in leads),
    )
    return sources, leads, summary


def run_sourcing_campaign_v2(
    campaign_target: CampaignTarget,
    source_count: int,
    lead_count: int,
    discovery_options: DiscoveryOptions,
) -> tuple[List[LeadSource], List[Lead], RunSummary, DiscoveryMetrics]:
    """V2: deterministic multi-provider discovery followed by V1 enrichment."""
    started_at = datetime.now(timezone.utc)
    run_id = str(uuid4())
    sources, discovery_metrics = discover_sources_v2(
        campaign_target,
        source_count,
        lead_count,
        discovery_options,
    )
    accumulated_leads: List[Lead] = []
    leads: List[Lead] = []
    for offset in range(0, len(sources), discovery_options.enrichment_batch_size):
        batch = sources[offset : offset + discovery_options.enrichment_batch_size]
        remaining = lead_count - len(leads)
        if remaining <= 0:
            break
        batch_leads = pull_leads(batch, min(remaining, len(batch)), campaign_target)
        accumulated_leads.extend(batch_leads)
        leads = score_and_deduplicate_leads(accumulated_leads)[:lead_count]
        discovery_metrics.enrichment_batches += 1
        discovery_metrics.sources_attempted += len(batch)
    discovery_metrics.leads_before_global_deduplication = len(accumulated_leads)
    for lead in leads:
        lead.run_id = run_id
    completed_at = datetime.now(timezone.utc)
    summary = RunSummary(
        run_id=run_id,
        campaign_id=campaign_target.campaign_id,
        campaign_name=campaign_target.campaign_name,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=round((completed_at - started_at).total_seconds(), 3),
        sources_discovered=len(sources),
        leads_returned=len(leads),
        verified_leads=sum(lead.verification_status == "verified" for lead in leads),
        enriched_leads=sum(lead.verification_status == "enriched" for lead in leads),
        incomplete_leads=sum(lead.verification_status == "incomplete" for lead in leads),
        discovery_metrics=discovery_metrics.model_dump(),
    )
    return sources, leads, summary, discovery_metrics


def build_lead_generation_workflow(
    source_count: int,
    lead_count: int,
    campaign_target: Optional[CampaignTarget] = None,
) -> Workflow:
    """Sequential multi-agent workflow: Business Research -> Lead Source
    Research -> Lead Puller, wired with Agno's native Workflow/Step so the
    whole pipeline can be run in a single call (workflow.run(url))."""
    max_retries = get_settings().WORKFLOW_STEP_MAX_RETRIES

    def _research_step(step_input: StepInput) -> StepOutput:
        url = step_input.get_input_as_string() or ""
        return StepOutput(content=research_business(url))

    def _source_step(step_input: StepInput) -> StepOutput:
        business_research: BusinessResearch = step_input.previous_step_content
        return StepOutput(content=find_lead_sources(business_research, source_count, campaign_target))

    def _puller_step(step_input: StepInput) -> StepOutput:
        lead_sources: List[LeadSource] = step_input.previous_step_content
        return StepOutput(content=pull_leads(lead_sources, lead_count, campaign_target))

    return Workflow(
        name="Lead Generation Pipeline",
        steps=[
            Step(name="Research Business", executor=_research_step, max_retries=max_retries),
            Step(name="Find Lead Sources", executor=_source_step, max_retries=max_retries),
            Step(name="Pull Leads", executor=_puller_step, max_retries=max_retries),
        ],
    )
