import unittest

from database import SCHEMA_SQL


class DatabaseSchemaTests(unittest.TestCase):
    def test_generated_lead_fields_are_persisted(self):
        for column in ("personal_email", "google_place_id", "google_maps_url"):
            self.assertIn(column, SCHEMA_SQL)

    def test_downstream_view_only_exposes_qualified_leads(self):
        self.assertIn("ad_generator_leads_v", SCHEMA_SQL)
        self.assertIn("'verified', 'enriched'", SCHEMA_SQL)


if __name__ == "__main__":
    unittest.main()
