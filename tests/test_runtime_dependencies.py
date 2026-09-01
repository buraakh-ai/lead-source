import sys
import types
import unittest
from unittest.mock import patch

from tools.google_places import google_places_error
from tools.scraping.scrapling_engine import ScraplingEngine


class RuntimeDependencyTests(unittest.TestCase):
    def test_scrapling_engine_uses_lightweight_static_fetcher(self):
        calls = []

        class FakeFetcher:
            @staticmethod
            def get(url, **kwargs):
                calls.append((url, kwargs))
                return types.SimpleNamespace(
                    html_content="<html><body>Useful content</body></html>",
                    status=200,
                )

        fake_fetchers = types.ModuleType("scrapling.fetchers")
        fake_fetchers.Fetcher = FakeFetcher
        with patch.dict(sys.modules, {"scrapling.fetchers": fake_fetchers}):
            result = ScraplingEngine().fetch("https://example.test")

        self.assertTrue(result.success)
        self.assertEqual(result.engine, "scrapling")
        self.assertEqual(calls[0][0], "https://example.test")
        self.assertEqual(calls[0][1]["impersonate"], "chrome")
        self.assertEqual(calls[0][1]["retries"], 1)

    def test_places_request_denied_has_actionable_safe_diagnostics(self):
        message = google_places_error("REQUEST_DENIED", "API key not valid")

        self.assertIn("Places API and billing", message)
        self.assertIn("restrictions", message)
        self.assertNotIn("AIza", message)


if __name__ == "__main__":
    unittest.main()
