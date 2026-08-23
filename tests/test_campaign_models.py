import unittest
from datetime import date

from schemas import CampaignTarget, LeadSource


class CampaignModelTests(unittest.TestCase):
    def test_dynamic_location_label(self):
        campaign = CampaignTarget(
            campaign_name="August Restaurants",
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            country="United States",
            state="California",
            cities_or_areas=["Orange County", "Irvine"],
            industries=["Restaurants"],
        )
        self.assertEqual(
            campaign.location_label(),
            "Orange County, Irvine, California, United States",
        )

    def test_public_source_business_evidence(self):
        source = LeadSource(
            source_name="Example Restaurant",
            url="https://example.test",
            why_relevant="Matches campaign",
            rating=4.7,
            review_count=125,
            business_status="OPERATIONAL",
            business_types=["restaurant", "food"],
        )
        self.assertEqual(source.review_count, 125)
        self.assertIn("restaurant", source.business_types)


if __name__ == "__main__":
    unittest.main()
