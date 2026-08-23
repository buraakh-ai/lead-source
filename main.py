"""CLI entry point: runs the full lead-generation pipeline against a single
business URL without needing FastAPI or Streamlit running. Useful for quick
local testing.

Usage: python main.py <url> [--sources N] [--leads N]
"""

import argparse
import logging

from dotenv import load_dotenv

load_dotenv()

from config.settings import get_settings  # noqa: E402

logging.basicConfig(
    level=logging.DEBUG if get_settings().DEBUG_MODE else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from orchestration.lead_pipeline import build_lead_generation_workflow  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the lead-generation pipeline against one business URL.")
    parser.add_argument("url", help="Business website URL to research")
    parser.add_argument("--sources", type=int, default=3, help="Number of lead sources to find (default: 3)")
    parser.add_argument("--leads", type=int, default=3, help="Number of leads to pull (default: 3)")
    args = parser.parse_args()

    workflow = build_lead_generation_workflow(args.sources, args.leads)
    run_output = workflow.run(input=args.url)

    business_research, lead_sources, leads = (step.content for step in run_output.step_results)

    print("\n=== Business Research ===")
    print(business_research.model_dump_json(indent=2))
    print("\n=== Lead Sources ===")
    for source in lead_sources:
        print(f"- {source.source_name}: {source.url}")
    print("\n=== Leads ===")
    for lead in leads:
        print(f"- {lead.name}: phone={lead.phone} email={lead.business_email or lead.personal_email}")


if __name__ == "__main__":
    main()
