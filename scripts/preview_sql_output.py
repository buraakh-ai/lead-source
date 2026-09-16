"""Preview destination rows without connecting to a database.

Run from the repository root:
    python scripts/preview_sql_output.py
    python scripts/preview_sql_output.py --input campaign-response.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import CampaignTarget, Lead, RunSummary
from shared_output import load_output_config, map_lead


def main():
    parser = argparse.ArgumentParser(description="Preview shared SQL rows; never connects to AWS.")
    parser.add_argument("--input", type=Path, help="Saved V1 or V2 campaign API response JSON")
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config/aws_output.example.json")
    args = parser.parse_args()
    config = load_output_config(str(args.config))
    now = datetime.now(timezone.utc)
    if args.input:
        payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
        campaign = CampaignTarget.model_validate(payload["campaign"])
        summary = RunSummary.model_validate(payload["run_summary"])
        leads = [Lead.model_validate(lead) for lead in payload["leads"]]
        label = "BACKEND RESPONSE"
    else:
        campaign = CampaignTarget(campaign_id="preview-campaign", campaign_name="Sample preview")
        summary = RunSummary(run_id="preview-run", campaign_id=campaign.campaign_id,
                             campaign_name=campaign.campaign_name, started_at=now,
                             completed_at=now, duration_seconds=0)
        leads = [
            Lead(name="Demo Restaurant", business_name="Demo Restaurant", category="Restaurant",
                 business_email="business@example.com", phone="+1-202-555-0100",
                 decision_maker_name="Alex Owner", marketing_notes="Illustrative sample only"),
            Lead(name="Hari Pandey", category="individual", personal_email="person@example.com",
                 phone="+1-202-555-0101", marketing_notes="Illustrative sample only"),
        ]
        label = "ILLUSTRATIVE SAMPLE DATA"
    print(f"{label} - SQL destination preview; no database connection", file=sys.stderr)
    print("id is omitted because the destination generates it. comment is a JSON string.", file=sys.stderr)
    rows = [map_lead(lead, campaign, summary, config, now) for lead in leads]
    print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
