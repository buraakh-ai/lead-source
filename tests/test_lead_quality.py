import unittest

from lead_quality import score_and_deduplicate_leads
from schemas import Lead


class LeadQualityTests(unittest.TestCase):
    def test_complete_lead_is_verified_and_scores_100(self):
        lead = Lead(name="Sample Cafe", business_name="Sample Cafe", website="https://sample.example", phone="(949) 555-0100", business_email="owner@sample.example", decision_maker_name="Alex Owner", decision_maker_role="Owner", linkedin_url="https://linkedin.com/in/alex-owner", source_urls=["https://sample.example/contact"])
        result = score_and_deduplicate_leads([lead])
        self.assertEqual(result[0].lead_score, 100)
        self.assertEqual(result[0].verification_status, "verified")

    def test_duplicate_domain_keeps_richer_record(self):
        sparse = Lead(name="Shop", website="https://shop.example", phone="9495550100")
        rich = Lead(name="Shop LLC", website="https://www.shop.example/about", phone="9495550100", business_email="hello@shop.example", source_url="https://shop.example/contact")
        result = score_and_deduplicate_leads([sparse, rich])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].business_email, "hello@shop.example")

    def test_records_are_sorted_by_score(self):
        lower = Lead(name="Lower", phone="9495550101")
        higher = Lead(name="Higher", phone="9495550102", business_email="hi@higher.example")
        result = score_and_deduplicate_leads([lower, higher])
        self.assertEqual(result[0].name, "Higher")


if __name__ == "__main__":
    unittest.main()
