"""Central LLM routing: pick a model by complexity tier instead of hardcoding
a provider per agent.

Tiers:
    "low"  - open-weight model served over a cloud API (Groq). Cheap/fast,
             meant for tasks that are mostly structured extraction/formatting.
    "high" - paid frontier model (OpenAI). Meant for tasks that need stronger
             reasoning (planning, multi-step tool orchestration, inference).

Whichever provider is preferred for a tier is tried first; if its API key
isn't configured, the router falls through to the other cloud provider, and
finally to local Ollama - so the app still runs with only one (or zero) API
keys configured, same as before this router existed.
"""

from typing import Any, Dict, List, Optional

from agno.models.base import Model
from agno.models.fallback import FallbackConfig
from agno.models.groq import Groq
from agno.models.ollama import Ollama
from agno.models.openai import OpenAIChat

from config.settings import ModelTier, Settings, get_settings

_TIER_PROVIDER_ORDER: Dict[ModelTier, List[str]] = {
    "low": ["groq", "openai", "ollama"],
    "high": ["openai", "groq", "ollama"],
}


class ModelRouter:
    """Resolves a complexity tier to a concrete Agno model, fallback config,
    and (when needed) parser model."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    def _retry_kwargs(self) -> Dict[str, Any]:
        return {
            "retries": self.settings.LLM_MAX_RETRIES,
            "delay_between_retries": self.settings.LLM_RETRY_DELAY_SECONDS,
            "exponential_backoff": True,
        }

    def _ollama_model(self) -> Ollama:
        return Ollama(id=self.settings.OLLAMA_MODEL_ID, host=self.settings.OLLAMA_HOST)

    def _primary_provider(self, tier: ModelTier) -> str:
        for provider in _TIER_PROVIDER_ORDER[tier]:
            if provider == "groq" and self.settings.GROQ_API_KEY:
                return "groq"
            if provider == "openai" and self.settings.OPENAI_API_KEY:
                return "openai"
            if provider == "ollama":
                return "ollama"
        return "ollama"  # unreachable - ollama always matches above

    def get_model(self, tier: ModelTier) -> Model:
        provider = self._primary_provider(tier)
        if provider == "groq":
            return Groq(id=self.settings.GROQ_MODEL_ID, api_key=self.settings.GROQ_API_KEY, **self._retry_kwargs())
        if provider == "openai":
            return OpenAIChat(
                id=self.settings.OPENAI_MODEL_ID, api_key=self.settings.OPENAI_API_KEY, **self._retry_kwargs()
            )
        return self._ollama_model()

    def get_fallback_config(self, tier: ModelTier) -> Optional[FallbackConfig]:
        # Nothing to fall back to if Ollama is already the primary model.
        if self._primary_provider(tier) == "ollama":
            return None
        fallback = [self._ollama_model()]
        return FallbackConfig(on_error=fallback, on_rate_limit=fallback)

    def get_parser_model(self, tier: ModelTier) -> Optional[Model]:
        # Groq's API rejects requests that combine tool/function calling with
        # JSON-schema structured output. When Groq is the resolved provider,
        # the primary model keeps its tools and replies in plain text, and
        # this second, tool-free call enforces the output_schema. OpenAI and
        # Ollama support tools + structured output in a single call.
        if self._primary_provider(tier) == "groq":
            return Groq(id=self.settings.GROQ_MODEL_ID, api_key=self.settings.GROQ_API_KEY, **self._retry_kwargs())
        return None

    def agent_kwargs(self, tier: ModelTier) -> Dict[str, Any]:
        """Convenience bundle of the kwargs every Agent builder needs."""
        return {
            "model": self.get_model(tier),
            "fallback_config": self.get_fallback_config(tier),
            "parser_model": self.get_parser_model(tier),
            "debug_mode": self.settings.DEBUG_MODE,
        }


def get_router() -> ModelRouter:
    return ModelRouter()
