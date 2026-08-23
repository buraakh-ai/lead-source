# from agno.agent import Agent

# from config.settings import get_settings
# from llm.router import get_router
# from prompts import load_prompt
# from schemas import LeadSourceList
# from tools import discover_contact_pages, google_places_search, web_search


# def build_lead_source_agent(source_count: int) -> Agent:
#     prompt = load_prompt("lead_source_agent", source_count=source_count)
#     router = get_router()
#     tier = get_settings().LEAD_SOURCE_TIER

#     return Agent(
#         name=prompt["name"],
#         **router.agent_kwargs(tier),
#         tools=[web_search, google_places_search, discover_contact_pages],
#         tool_call_limit=source_count * 2 + 4,
#         output_schema=LeadSourceList,
#         instructions=prompt["instructions"],
#         markdown=False,
#     )
from agno.agent import Agent

from config.settings import get_settings
from llm.router import get_router
from prompts import load_prompt
from schemas import LeadSourceList
from tools import (
    discover_contact_pages,
    google_places_search,
    web_search,
)


def build_lead_source_agent(source_count: int) -> Agent:
    prompt = load_prompt(
        "lead_source_agent",
        source_count=source_count,
    )
    router = get_router()
    tier = get_settings().LEAD_SOURCE_TIER

    return Agent(
        name=prompt["name"],
        **router.agent_kwargs(tier),
        tools=[
            web_search,
            google_places_search,
            discover_contact_pages,
        ],
        tool_call_limit=source_count * 3 + 6,
        output_schema=LeadSourceList,
        instructions=prompt["instructions"],
        markdown=False,
    )
