from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

ModelTier = Literal["low", "high"]


class Settings(BaseSettings):
    """Single source of truth for every environment-configurable knob in the
    project, including every max-attempts/retry cap that bounds a loop."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=True)

    # --- LLM providers -----------------------------------------------------
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL_ID: str = "llama-3.3-70b-versatile"

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL_ID: str = "gpt-4o"

    OLLAMA_MODEL_ID: str = "qwen2.5:7b"
    OLLAMA_HOST: Optional[str] = None

    # --- LLM router ----------------------------------------------------------
    # "low" = open-weight model served over a cloud API (Groq). "high" = paid
    # frontier model (OpenAI). Local Ollama is always the last-resort offline
    # fallback for either tier, regardless of these settings.
    BUSINESS_RESEARCH_TIER: ModelTier = "high"
    LEAD_SOURCE_TIER: ModelTier = "high"
    LEAD_PULLER_TIER: ModelTier = "high"

    # Retries on the primary model itself (rate-limit/transient errors) before
    # falling back to the next model in the chain.
    LLM_MAX_RETRIES: int = 2
    LLM_RETRY_DELAY_SECONDS: int = 10

    # --- Search / places APIs ------------------------------------------------
    SERP_API_KEY: Optional[str] = None
    GOOGLE_PLACES_API_KEY: Optional[str] = None

    # --- Web scraping fallback chain ------------------------------------------
    # Hard cap on how many engines the fallback chain will try for a single
    # URL (requests -> scrapling -> crawl4ai -> playwright). Prevents a
    # pathological URL from looping through engines indefinitely.
    SCRAPER_MAX_ATTEMPTS: int = 4
    SCRAPER_REQUEST_TIMEOUT_SECONDS: int = 10
    PLAYWRIGHT_TIMEOUT_MS: int = 15000

    # --- Orchestration ---------------------------------------------------------
    # Max retries Agno's Workflow/Step machinery will attempt for a single
    # step before giving up on that stage.
    WORKFLOW_STEP_MAX_RETRIES: int = 3

    # --- Frontend --------------------------------------------------------------
    BACKEND_URL: str = "http://localhost:8000"

    # --- Central AWS PostgreSQL database --------------------------------------
    # Example only: postgresql://user:password@host:5432/database?sslmode=require
    # Keep the real value in .env or an AWS secret, never in source control.
    AWS_POSTGRES_DSN: Optional[str] = None
    DATABASE_AUTO_CREATE_TABLES: bool = True

    # --- Debugging ---------------------------------------------------------------
    DEBUG_MODE: bool = False
    # Emit each discovered source and lead as one structured JSON log line.
    # Useful for the backend-only AWS proof of concept; disable after the
    # PostgreSQL handoff is enabled if contact data should not remain in logs.
    LOG_SOURCING_DETAILS: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
