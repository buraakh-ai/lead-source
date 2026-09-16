"""Opt-in export to the shared lead table; no schema changes or other-source updates."""

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from schemas import CampaignTarget, Lead, RunSummary


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_name: str = Field(min_length=1)
    table_name: str = Field(min_length=1)
    source_name: str = "leadsource"
    source_type: str = "web_scraping"
    business_source_id: str = "lead:0"
    individual_source_id: str = "lead:1"


def load_output_config(path: str) -> OutputConfig:
    return OutputConfig.model_validate_json(Path(path).read_text(encoding="utf-8"))


def map_lead(lead: Lead, campaign: CampaignTarget, summary: RunSummary,
             config: OutputConfig, loaded_at: datetime) -> dict:
    # Existing category describes an industry. Only explicit 'individual' opts
    # into person mapping; finding a business owner does not reclassify a business.
    individual = (lead.category or "").strip().casefold() == "individual"
    first_name = last_name = None
    if individual:
        parts = (lead.decision_maker_name or lead.name).strip().split(maxsplit=1)
        first_name = parts[0] if parts else None
        last_name = parts[1] if len(parts) > 1 else None
    return {
        "business_name": lead.business_name if individual else (lead.business_name or lead.name),
        "category": "individual" if individual else "business",
        "source_id": config.individual_source_id if individual else config.business_source_id,
        "source_name": config.source_name,
        "source_type": config.source_type,
        "first_name": first_name,
        "last_name": last_name,
        "email": (lead.personal_email or lead.business_email) if individual else lead.business_email,
        "phone": lead.phone,
        # The destination has no enrichment columns. Preserve the complete lead
        # and campaign in comment rather than silently discarding those fields.
        "comment": json.dumps({"lead": lead.model_dump(mode="json"),
                               "campaign": campaign.model_dump(mode="json"),
                               "run_id": summary.run_id}, ensure_ascii=False),
        "loaded_at": loaded_at,
        "webinar_id": None,
        "file_name": None,
    }


def persist_shared_output(dsn: str, config: OutputConfig, campaign: CampaignTarget,
                          leads: list[Lead], summary: RunSummary) -> tuple[bool, str]:
    import psycopg
    from psycopg import sql

    if not leads:
        return True, "No qualified leads to save to the shared destination."
    loaded_at = datetime.now(timezone.utc)
    rows = [map_lead(lead, campaign, summary, config, loaded_at) for lead in leads]
    columns = list(rows[0])
    statement = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
        sql.Identifier(config.schema_name), sql.Identifier(config.table_name),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    with psycopg.connect(dsn, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(statement, [tuple(row[column] for column in columns) for row in rows])
    return True, f"Saved {len(rows)} leads to the shared AWS PostgreSQL destination."
