import unittest
from unittest.mock import patch

from orchestration.discovery_v2 import Candidate, build_discovery_plan, discover_sources_v2
from orchestration.lead_pipeline import run_sourcing_campaign_v2
from schemas import CampaignTarget, DiscoveryMetrics, DiscoveryOptions, Lead, LeadSource


class DiscoveryV2Tests(unittest.TestCase):
    def test_plan_covers_each_location_category_and_provider(self):
        campaign = CampaignTarget(
            cities_or_areas=["Irvine", "Tustin"],
            industries=["Restaurants"],
            subcategories=["Coffee shops"],
        )
        options = DiscoveryOptions(providers=["google_places", "yellow_pages"], max_queries=20)

        plan = build_discovery_plan(campaign, options)

        self.assertEqual(len(plan), 8)
        self.assertEqual({item.location for item in plan}, {"Irvine", "Tustin"})
        self.assertEqual({item.category for item in plan}, {"Restaurants", "Coffee shops"})

    def test_discovery_deduplicates_and_reports_rejections(self):
        campaign = CampaignTarget(cities_or_areas=["Irvine"], industries=["Restaurants"])
        options = DiscoveryOptions(
            providers=["yellow_pages"],
            oversampling_factor=3,
            max_queries=5,
            results_per_query=10,
            max_pages_per_query=1,
        )

        def fake_fetcher(query, page, page_size):
            return [
                Candidate("yellow_pages", "Alpha Cafe", "https://yellowpages.com/alpha", query.category, query.location),
                Candidate("yellow_pages", "Beta Cafe", "https://yellowpages.com/beta", query.category, query.location),
                Candidate("yellow_pages", "Alpha Cafe", "https://yellowpages.com/alpha-duplicate", query.category, query.location),
                Candidate("yellow_pages", "", "https://yellowpages.com/missing", query.category, query.location),
            ], None, None

        sources, metrics = discover_sources_v2(
            campaign,
            source_count=10,
            lead_count=3,
            options=options,
            provider_fetchers={"yellow_pages": fake_fetcher},
        )

        self.assertEqual([source.source_name for source in sources], ["Alpha Cafe", "Beta Cafe"])
        self.assertEqual(metrics.raw_candidates, 4)
        self.assertEqual(metrics.unique_candidates, 2)
        self.assertEqual(metrics.rejection_counts, {"duplicate": 1, "missing_name": 1})
        self.assertTrue(metrics.exhausted_before_target)

    def test_google_places_candidates_are_distinct_by_place_id(self):
        campaign = CampaignTarget(cities_or_areas=["Irvine"], industries=["Restaurants"])
        options = DiscoveryOptions(providers=["google_places"], max_pages_per_query=1)

        def fake_fetcher(query, page, page_size):
            return [
                Candidate("google_places", "One", "https://google.com/maps/one", query.category, query.location, place_id="one"),
                Candidate("google_places", "Two", "https://google.com/maps/two", query.category, query.location, place_id="two"),
            ], None, None

        sources, metrics = discover_sources_v2(
            campaign, 10, 2, options, {"google_places": fake_fetcher}
        )

        self.assertEqual(len(sources), 2)
        self.assertEqual(metrics.unique_candidates, 2)

    def test_custom_provider_uses_the_standard_source_contract_and_deduplication(self):
        campaign = CampaignTarget(cities_or_areas=["Irvine"], industries=["Restaurants"])
        options = DiscoveryOptions(providers=["new_public_source"], max_pages_per_query=1)

        def fake_fetcher(query, page, page_size):
            candidate = Candidate(
                query.provider,
                "Example Cafe",
                "https://example.test/contact",
                query.category,
                query.location,
            )
            return [candidate, candidate], None, None

        sources, metrics = discover_sources_v2(
            campaign, 10, 2, options, {"new_public_source": fake_fetcher}
        )

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].source_type, "new_public_source")
        self.assertEqual(set(sources[0].model_dump()), set(LeadSource.model_fields))
        self.assertEqual(metrics.rejection_counts, {"duplicate": 1})

    @patch("orchestration.lead_pipeline.pull_leads")
    @patch("orchestration.lead_pipeline.discover_sources_v2")
    def test_v2_enriches_sources_in_bounded_batches(self, discover_mock, pull_mock):
        campaign = CampaignTarget(cities_or_areas=["Irvine"], industries=["Restaurants"])
        sources = [
            LeadSource(source_name=f"Business {index}", url=f"https://b{index}.example", why_relevant="test")
            for index in range(5)
        ]
        metrics = DiscoveryMetrics(
            requested_sources=5,
            requested_leads=4,
            raw_candidate_target=15,
            unique_candidates=5,
            sources_selected=5,
        )
        discover_mock.return_value = (sources, metrics)
        pull_mock.side_effect = lambda batch, count, target: [
            Lead(name=source.source_name, website=source.url, phone=f"555-010{index}")
            for index, source in enumerate(batch[:count])
        ]

        _, leads, summary, result_metrics = run_sourcing_campaign_v2(
            campaign,
            source_count=5,
            lead_count=4,
            discovery_options=DiscoveryOptions(enrichment_batch_size=2),
        )

        self.assertEqual(len(leads), 4)
        self.assertEqual(pull_mock.call_count, 2)
        self.assertEqual(result_metrics.enrichment_batches, 2)
        self.assertEqual(result_metrics.sources_attempted, 4)
        self.assertEqual(summary.discovery_metrics["enrichment_batches"], 2)


if __name__ == "__main__":
    unittest.main()
