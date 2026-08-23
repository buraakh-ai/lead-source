from agno.agent import Agent

from agents.skill_registry import get_skills
from config.settings import get_settings
from llm.router import get_router
from prompts import load_prompt
from schemas import BusinessResearch
from tools import fetch_webpage_text


def build_business_research_agent() -> Agent:
    prompt = load_prompt("business_research_agent")
    router = get_router()
    tier = get_settings().BUSINESS_RESEARCH_TIER

    return Agent(
        name=prompt["name"],
        **router.agent_kwargs(tier),
        tools=[fetch_webpage_text],
        skills=get_skills(),
        tool_call_limit=4,
        output_schema=BusinessResearch,
        instructions=prompt["instructions"],
        markdown=False,
    )
