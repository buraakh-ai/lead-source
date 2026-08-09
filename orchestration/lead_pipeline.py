from typing import List

from agno.utils.log import log_info
from agno.workflow import Step, StepInput, StepOutput, Workflow

from agents import build_business_research_agent, build_lead_puller_agent, build_lead_source_agent
from config.settings import get_settings
from schemas import BusinessResearch, Lead, LeadList, LeadSource, LeadSourceList

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


def find_lead_sources(business_research: BusinessResearch, source_count: int) -> List[LeadSource]:
    """Stage 2: find candidate lead-source web pages for the business's ICP."""
    log_info(f"[Pipeline] Stage 2/3: researching {source_count} lead sources")
    agent = build_lead_source_agent(source_count)
    agent_input = (
        f"Target business research:\n{business_research.model_dump_json(indent=2)}\n\n"
        f"Find exactly {source_count} lead source pages."
    )
    result: LeadSourceList = agent.run(input=agent_input).content
    sources = result.sources[:source_count]
    log_info(f"[Pipeline] Lead source research done: found {len(sources)} sources")
    return sources


def pull_leads(lead_sources: List[LeadSource], lead_count: int) -> List[Lead]:
    """Stage 3: pull and validate lead contact details from the source pages."""
    log_info(f"[Pipeline] Stage 3/3: pulling up to {lead_count} leads from {len(lead_sources)} sources")
    agent = build_lead_puller_agent(lead_count)
    agent_input = (
        "Lead source pages to pull from:\n"
        f"{LeadSourceList(sources=lead_sources).model_dump_json(indent=2)}\n\n"
        f"Pull at most {lead_count} leads."
    )
    result: LeadList = agent.run(input=agent_input).content

    valid_leads = [
        lead
        for lead in result.leads
        if lead.name and (lead.phone or lead.business_email or lead.personal_email or lead.linkedin_url)
    ]
    leads = valid_leads[:lead_count]
    log_info(f"[Pipeline] Lead pulling done: {len(leads)} valid leads out of {len(result.leads)} returned")
    return leads


def build_lead_generation_workflow(source_count: int, lead_count: int) -> Workflow:
    """Sequential multi-agent workflow: Business Research -> Lead Source
    Research -> Lead Puller, wired with Agno's native Workflow/Step so the
    whole pipeline can be run in a single call (workflow.run(url))."""
    max_retries = get_settings().WORKFLOW_STEP_MAX_RETRIES

    def _research_step(step_input: StepInput) -> StepOutput:
        url = step_input.get_input_as_string() or ""
        return StepOutput(content=research_business(url))

    def _source_step(step_input: StepInput) -> StepOutput:
        business_research: BusinessResearch = step_input.previous_step_content
        return StepOutput(content=find_lead_sources(business_research, source_count))

    def _puller_step(step_input: StepInput) -> StepOutput:
        lead_sources: List[LeadSource] = step_input.previous_step_content
        return StepOutput(content=pull_leads(lead_sources, lead_count))

    return Workflow(
        name="Lead Generation Pipeline",
        steps=[
            Step(name="Research Business", executor=_research_step, max_retries=max_retries),
            Step(name="Find Lead Sources", executor=_source_step, max_retries=max_retries),
            Step(name="Pull Leads", executor=_puller_step, max_retries=max_retries),
        ],
    )
