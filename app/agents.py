import os
from typing import Any, Dict, Optional

from agno.agent import Agent
from agno.models.base import Model
from agno.models.fallback import FallbackConfig
from agno.models.groq import Groq
from agno.models.ollama import Ollama
from agno.models.openai import OpenAIChat

from .schemas import BusinessResearch, LeadList, LeadSourceList
from .tools import discover_contact_pages, fetch_webpage_text, google_places_search, scrape_contacts, web_search

# Retry the primary cloud model itself (with backoff) before giving up on it.
# Rate-limit (429) responses are retryable by default in Agno, so this waits out
# short-lived per-minute token/request caps (~10s, then ~20s) instead of
# immediately degrading every call to the local fallback model on the first 429.
_RETRY_KWARGS: Dict[str, Any] = {
    "retries": 2,
    "delay_between_retries": 10,
    "exponential_backoff": True,
}


def _ollama_model() -> Ollama:
    return Ollama(
        id=os.getenv("OLLAMA_MODEL_ID", "qwen2.5:7b"),
        host=os.getenv("OLLAMA_HOST"),
    )


def _model() -> Model:
    # Prefer Groq if configured, then OpenAI, then fall straight to the local
    # no-cost Ollama model if neither cloud API key is set.
    if os.getenv("GROQ_API_KEY"):
        return Groq(id=os.getenv("GROQ_MODEL_ID", "llama-3.3-70b-versatile"), **_RETRY_KWARGS)
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIChat(id=os.getenv("OPENAI_MODEL_ID", "gpt-4o"), **_RETRY_KWARGS)
    return _ollama_model()


def _fallback_config() -> Optional[FallbackConfig]:
    # Once the primary model's own retries (above) are exhausted - i.e. we're
    # still rate-limited after waiting it out - fall back to the local, no-cost
    # Ollama model instead of failing the run outright. Nothing to fall back to
    # if Ollama is already the primary model.
    if not (os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")):
        return None
    fallback = [_ollama_model()]
    return FallbackConfig(on_error=fallback, on_rate_limit=fallback)


def _debug_mode() -> bool:
    # Controlled by DEBUG_MODE in .env. When on, Agno streams verbose per-agent
    # tool-call/reasoning traces to the console (in addition to the pipeline's
    # own INFO-level progress logs, which always show regardless of this flag).
    return os.getenv("DEBUG_MODE", "false").strip().lower() in ("1", "true", "yes", "on")


def _parser_model() -> Optional[Model]:
    # Groq's API rejects requests that combine tool/function calling with JSON-schema
    # structured output ("json mode cannot be combined with tool/function calling").
    # Agno's fix for this is a parser_model: the primary model keeps its tools and
    # replies in plain text, then this second, tool-free call enforces output_schema.
    # OpenAI and Ollama support tools + structured output in a single call, so they
    # don't need this extra pass.
    if os.getenv("GROQ_API_KEY"):
        return Groq(id=os.getenv("GROQ_MODEL_ID", "llama-3.3-70b-versatile"), **_RETRY_KWARGS)
    return None


def _agent_kwargs() -> Dict[str, Any]:
    return {
        "model": _model(),
        "fallback_config": _fallback_config(),
        "parser_model": _parser_model(),
        "debug_mode": _debug_mode(),
    }


def build_business_research_agent() -> Agent:
    return Agent(
        name="Business Research Agent",
        **_agent_kwargs(),
        tools=[fetch_webpage_text],
        tool_call_limit=4,
        output_schema=BusinessResearch,
        instructions=[
            "You are given a business website URL.",
            "Call fetch_webpage_text on the URL to read the homepage, then call it again on "
            "AT MOST 2 internal_links that look like About/Services/Contact pages - never "
            "more than 3 fetch_webpage_text calls in total.",
            "Determine: the business name, its primary location (city/state or region), the "
            "services/products it offers, and any notable branding or positioning details.",
            "For the ICP (ideal customer profile), think about WHO this business sells to, "
            "not what it does. A tax consultancy's ICP is 'small businesses like "
            "restaurants, clinics, and salons that need bookkeeping/tax help' - NOT other "
            "tax consultancies. A marketing agency's ICP is its potential clients (e.g. "
            "law firms, gyms, contractors) - NOT other marketing agencies. Never let icp or "
            "icp_categories describe the same industry as the target business itself.",
            "In icp_categories, list 3-6 short, generic, searchable category terms for "
            "those customer businesses (e.g. 'restaurants', 'hair salons', 'dental "
            "clinics') - these will be used verbatim as Google Places/Search queries.",
            "Base every field strictly on what you actually read from the pages. If something "
            "is not stated, make a reasonable inference from context rather than inventing facts.",
        ],
        markdown=False,
    )


# def build_lead_source_agent(source_count: int) -> Agent:
#     return Agent(
#         name="Lead Source Research Agent",
#         **_agent_kwargs(),
#         tools=[web_search, google_places_search, discover_contact_pages],
#         tool_call_limit=source_count * 2 + 4,
#         output_schema=LeadSourceList,
#         instructions=[
#             "You receive a JSON summary of a target business, including icp_categories - a "
#             "list of concrete categories of OTHER small businesses that are the target's "
#             "potential CUSTOMERS (not competitors). Leads must come from these categories.",
#             "Find real, publicly accessible web pages belonging to small businesses in "
#             "icp_categories, located in the same area as the target business.",
#             "Never search for or return businesses in the same category as the target "
#             "business itself - those are competitors, not leads.",
#             "Prefer direct Contact-us or About-us pages of small business websites, since "
#             "contact details (phone, business/personal email, or LinkedIn URL) are most "
#             "likely to appear there.",
#             "Call google_places_search using query=<one of the icp_categories> and "
#             "location=<the target business's location>, one call per category, until you "
#             "have enough candidates with a website - typically 1-3 calls covering different "
#             "icp_categories is enough. Each result already includes a website when available.",
#             "For a candidate whose website from google_places_search is just a homepage, "
#             "call discover_contact_pages(website) first - it's free (uses the site's own "
#             "sitemap, no search budget spent) and often finds the exact Contact/About page.",
#             "Only call web_search if discover_contact_pages found nothing useful for that "
#             "candidate, to locate their contact/about page, e.g. 'site:<domain> contact'. "
#             f"Pass num_results=3 and call it at most {source_count} times total across the "
#             "whole task - never once per candidate if you already have enough good sources.",
#             "Never use paid lead databases or aggregators (e.g. Apollo, ZoomInfo, Clearbit). "
#             "Only use pages you actually found via google_places_search, "
#             "discover_contact_pages, or web_search.",
#             "If the best page you found is not itself a direct contact page (e.g. it's a "
#             "homepage or directory listing), set stitching_instructions explaining exactly "
#             "which additional pages or steps to combine to reach real contact details.",
#             f"Return exactly {source_count} sources, ranked by likelihood of yielding a "
#             "usable lead. Stop calling tools as soon as you have enough candidates.",
#         ],
#         markdown=False,
#     )
def build_lead_source_agent(source_count: int) -> Agent:
    return Agent(
        name="Lead Source Research Agent",
        **_agent_kwargs(),
        tools=[
            web_search,
            google_places_search,
            discover_contact_pages,
        ],
        tool_call_limit=source_count * 2 + 4,
        output_schema=LeadSourceList,
        instructions=[
            "You receive a JSON summary of a target business, including "
            "icp_categories—a list of concrete categories of OTHER small "
            "businesses that are the target's potential CUSTOMERS, not "
            "competitors. Leads must come from these categories.",

            "Find real, publicly accessible web pages belonging to small "
            "businesses in icp_categories, located in the same area as the "
            "target business.",

            "Never search for or return businesses in the same category as "
            "the target business itself. Those are competitors, not leads.",

            "Prefer direct Contact-us or About-us pages of small business "
            "websites because contact details such as phone numbers, email "
            "addresses, or LinkedIn URLs are more likely to appear there.",

            "Call google_places_search using query= and "
            "location=<the target business's location>. Make one call per "
            "category until you have enough candidates with websites. "
            "Typically, 1-3 calls covering different icp_categories is enough. "
            "Each result already includes a website when available.",

            "For a candidate whose website from google_places_search is only "
            "a homepage, call discover_contact_pages(website) first. It uses "
            "the website's own sitemap and may find the exact Contact or About "
            "page.",

            "Only call web_search if discover_contact_pages found nothing "
            "useful for that candidate. Use it to locate the business's "
            "contact or about page.",

            f"When using web_search, pass num_results=3 and call it at most "
            f"{source_count} times across the entire task. Do not call it for "
            "every candidate when you already have enough verified sources.",

            "Never use paid lead databases or aggregators such as Apollo, "
            "ZoomInfo, or Clearbit. Only use pages actually found through "
            "google_places_search, discover_contact_pages, or web_search.",

            "If the best page found is not a direct contact page, such as a "
            "homepage or directory listing, set stitching_instructions to "
            "explain which additional page or step should be used to find "
            "real contact information.",

            # Original instruction:
            # f"Return exactly {source_count} sources, ranked by likelihood of "
            # "yielding a usable lead. Stop calling tools as soon as you have "
            # "enough candidates.",

            # New verification instructions:
            "Never invent, guess, or construct a business name, domain, or URL.",

            "Every returned business name and URL must come verbatim from a "
            "tool result produced during the current run.",

            "Before returning a source, confirm that its URL was found through "
            "google_places_search, discover_contact_pages, or web_search.",

            "Do not transform a business name into a guessed domain. For "
            "example, do not turn 'Tustin Wedding Venue' into a fabricated URL "
            "such as 'tustinweddingvenue.com'.",

            "Do not return placeholder domains, example URLs, or URLs based "
            "only on your general knowledge.",

            "If fewer verified sources are available, return fewer sources "
            "instead of inventing sources to reach the requested count.",

            f"Return up to {source_count} verified sources, ranked by their "
            "likelihood of yielding usable contact information. Stop calling "
            "tools when you have enough verified candidates.",
        ],
        markdown=False,
    )

def build_lead_puller_agent(lead_count: int) -> Agent:
    return Agent(
        name="Lead Puller Agent",
        **_agent_kwargs(),
        tools=[scrape_contacts, discover_contact_pages],
        tool_call_limit=lead_count * 3,
        output_schema=LeadList,
        instructions=[
            "You receive a JSON list of source web pages, each possibly with "
            "stitching_instructions.",
            "For each source, call scrape_contacts on its url ONCE. If that returns no "
            "emails, phones, or linkedin_urls: first try discover_contact_pages(url) to find "
            "the site's real Contact/About page via its sitemap (free, no search budget), "
            "and call scrape_contacts on the best candidate it returns; only use the tool's "
            "own follow_links as a fallback if discover_contact_pages finds nothing.",
            f"Never call scrape_contacts or discover_contact_pages more than {lead_count * 3} "
            "times combined in total across the whole task.",
            "A lead is only valid if you have the lead's name AND at least one of: phone, "
            "business email, personal email, or LinkedIn URL. Use candidate_name_hints, "
            "page_title, or the business name context to determine the name (use the business "
            "name itself if no individual person's name is identifiable).",
            "Do not invent contact details that were not returned by scrape_contacts.",
            f"Return at most {lead_count} leads, prioritizing sources with the richest "
            "contact data. Stop calling tools as soon as you have enough valid leads.",
        ],
        markdown=False,
    )
