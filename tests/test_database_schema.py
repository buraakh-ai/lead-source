import inspect
import unittest
from datetime import datetime, timezone

import database
from schemas import CampaignTarget, Lead, LeadSource, RunSummary


class RecordingCursor:
    def __init__(self, existing=False):
        self.existing = existing
        self.pending = None
        self.statements = []

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        if normalized.count("%s") != len(params):
            raise AssertionError(
                f"SQL has {normalized.count('%s')} placeholders for {len(params)} values"
            )
        self.statements.append((normalized, params))
        if normalized.startswith("SELECT company_id"):
            self.pending = (101,) if self.existing else None
        elif normalized.startswith("SELECT lead_id"):
            self.pending = (201,) if self.existing else None
        elif normalized.startswith("SELECT social_id"):
            self.pending = (301,) if self.existing else None
        elif "RETURNING company_id" in normalized:
            self.pending = (101,)
        elif "RETURNING lead_id" in normalized:
            self.pending = (201,)
        else:
            self.pending = None

    def fetchone(self):
        return self.pending


class DatabasePersistenceTests(unittest.TestCase):
    def setUp(self):
        now = datetime.now(timezone.utc)
        self.campaign = CampaignTarget(
            campaign_id="campaign-1", industries=["Restaurants"], cities_or_areas=["Irvine"]
        )
        self.summary = RunSummary(
            run_id="run-1", campaign_id="campaign-1", campaign_name="Test",
            started_at=now, completed_at=now, duration_seconds=1,
        )
        self.source = LeadSource(
            source_name="Cafe One", url="https://www.cafe.example/contact",
            why_relevant="test", category="Restaurant", city="Irvine",
        )
        self.lead = Lead(
            name="Cafe One", business_name="Cafe One", category="Restaurant",
            website="https://cafe.example", business_email="owner@cafe.example",
            phone="555-0100", decision_maker_name="Alex Owner",
            decision_maker_role="Owner", linkedin_url="https://linkedin.com/in/alex",
            source_urls=["https://cafe.example/contact"], verification_status="verified",
        )

    def test_insert_mapping_targets_all_three_qualified_tables(self):
        cursor = RecordingCursor()
        company_id = database._upsert_company(cursor, self.source, self.campaign, self.summary)
        lead_id = database._upsert_lead(cursor, self.lead, company_id, self.campaign, self.summary)
        database._upsert_social_profile(cursor, lead_id, self.lead)

        sql = "\n".join(statement for statement, _ in cursor.statements)
        self.assertIn("INSERT INTO leadsource.companies", sql)
        self.assertIn("INSERT INTO leadsource.leads", sql)
        self.assertIn("INSERT INTO leadsource.social_profiles", sql)

    def test_retry_paths_update_instead_of_delete_or_duplicate_insert(self):
        cursor = RecordingCursor(existing=True)
        company_id = database._upsert_company(cursor, self.lead, self.campaign, self.summary)
        lead_id = database._upsert_lead(cursor, self.lead, company_id, self.campaign, self.summary)
        database._upsert_social_profile(cursor, lead_id, self.lead)

        sql = "\n".join(statement for statement, _ in cursor.statements)
        self.assertIn("UPDATE leadsource.companies", sql)
        self.assertIn("UPDATE leadsource.leads", sql)
        self.assertIn("UPDATE leadsource.social_profiles", sql)
        self.assertNotIn("DELETE FROM", sql)

    def test_runtime_contains_no_ddl_or_legacy_table_writes(self):
        source = inspect.getsource(database)
        self.assertNotIn("CREATE TABLE", source)
        for legacy_table in (
            "lead_sourcing_campaigns", "lead_sourcing_runs",
            "lead_sourcing_sources", "lead_sourcing_leads",
        ):
            self.assertNotIn(legacy_table, source)

    def test_domain_normalization_supports_idempotent_company_matching(self):
        self.assertEqual(database._domain("https://www.Example.com/contact"), "example.com")
        self.assertEqual(database._domain("example.com"), "example.com")
        self.assertIsNone(database._domain("https://www.yellowpages.com/irvine-ca/example"))


if __name__ == "__main__":
    unittest.main()
