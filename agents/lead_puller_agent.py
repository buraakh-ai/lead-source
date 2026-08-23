from agno.agent import Agent

from config.settings import get_settings
from llm.router import get_router
from prompts import load_prompt
from schemas import LeadList
from tools import discover_contact_pages, scrape_contacts, web_search


def build_lead_puller_agent(lead_count: int) -> Agent:
    max_lookups = lead_count * 4
    prompt = load_prompt("lead_puller_agent", lead_count=lead_count, max_lookups=max_lookups)
    router = get_router()
    tier = get_settings().LEAD_PULLER_TIER

    return Agent(
        name=prompt["name"],
        **router.agent_kwargs(tier),
        tools=[scrape_contacts, discover_contact_pages, web_search],
        tool_call_limit=max_lookups,
        output_schema=LeadList,
        instructions=prompt["instructions"],
        markdown=False,
    )
