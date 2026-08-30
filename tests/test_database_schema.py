import unittest
from pathlib import Path

from database import SCHEMA_PATH, SCHEMA_SQL


class DatabaseSchemaTests(unittest.TestCase):
    def test_runtime_uses_checked_in_schema_template(self):
        self.assertEqual(SCHEMA_PATH, Path(__file__).resolve().parents[1] / "sql" / "001_create_lead_database.sql")
        self.assertEqual(SCHEMA_SQL, SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_generated_lead_fields_are_persisted(self):
        for column in ("personal_email", "google_place_id", "google_maps_url"):
            self.assertIn(column, SCHEMA_SQL)

    def test_downstream_view_only_exposes_qualified_leads(self):
        self.assertIn("ad_generator_leads_v", SCHEMA_SQL)
        self.assertIn("'verified', 'enriched'", SCHEMA_SQL)


if __name__ == "__main__":
    unittest.main()
