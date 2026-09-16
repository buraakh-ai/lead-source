import json
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from schemas import CampaignTarget, Lead, RunSummary
from shared_output import OutputConfig, map_lead, persist_shared_output


class SharedOutputTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.config = OutputConfig(schema_name="public", table_name="leads")
        self.campaign = CampaignTarget()
        self.summary = RunSummary(run_id="demo", campaign_id=self.campaign.campaign_id,
                                  campaign_name="Demo", started_at=self.now,
                                  completed_at=self.now, duration_seconds=0)

    def map(self, **values):
        return map_lead(Lead(**values), self.campaign, self.summary, self.config, self.now)

    def test_business_owner_does_not_turn_business_into_person(self):
        row = self.map(name="Lazy dog", category="Restaurant", decision_maker_name="Hari Pandey",
                       business_email="lazy@example.com", personal_email="hari@example.com")
        self.assertEqual(row["category"], "business")
        self.assertEqual(row["source_id"], "lead:0")
        self.assertIsNone(row["first_name"])
        self.assertIsNone(row["last_name"])
        self.assertEqual(row["email"], "lazy@example.com")
        self.assertNotIn("id", row)
        self.assertEqual(json.loads(row["comment"])["lead"]["personal_email"], "hari@example.com")

    def test_individual_and_missing_optional_fields(self):
        row = self.map(name="Hari Pandey", category="individual", personal_email="hr@example.com")
        self.assertEqual((row["first_name"], row["last_name"]), ("Hari", "Pandey"))
        self.assertEqual(row["source_id"], "lead:1")
        self.assertIsNone(row["business_name"])
        self.assertIsNone(row["webinar_id"])
        self.assertIsNone(row["file_name"])
        self.assertIsNone(self.map(name="Hari", category="individual")["last_name"])

    def test_configurable_source_ids(self):
        self.config.business_source_id = "3"
        self.assertEqual(self.map(name="Cafe")["source_id"], "3")

    @patch("psycopg.connect")
    def test_transaction_uses_shared_table_and_parameterized_values(self, connect):
        connection = connect.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        result = persist_shared_output("unused", self.config, self.campaign,
                                       [Lead(name="O'Brien")], self.summary)
        self.assertTrue(result[0])
        statement, values = cursor.executemany.call_args.args
        query = statement.as_string()
        self.assertIn('INSERT INTO "public"."leads"', query)
        self.assertNotIn("O'Brien", query)
        self.assertEqual(values[0][0], "O'Brien")
        self.assertEqual(query.count("%s"), len(values[0]))

    @patch("psycopg.connect")
    def test_write_failure_exits_transaction_with_error(self, connect):
        connection = connect.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.executemany.side_effect = RuntimeError("write failed")
        with self.assertRaises(RuntimeError):
            persist_shared_output("unused", self.config, self.campaign, [Lead(name="Cafe")], self.summary)
        self.assertEqual(connect.return_value.__exit__.call_args.args[0], RuntimeError)


if __name__ == "__main__":
    unittest.main()
