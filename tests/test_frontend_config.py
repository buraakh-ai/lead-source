import json
import tempfile
import unittest
from pathlib import Path

from frontend.config_loader import load_config


class FakeBody:
    def __init__(self, value):
        self.value = value

    def read(self):
        return self.value


class FakeS3Client:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def get_object(self, **kwargs):
        self.request = kwargs
        return {"Body": FakeBody(self.payload)}


class FrontendConfigTests(unittest.TestCase):
    def test_partial_local_override_is_merged_with_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"campaign": {"default_name": "AWS Campaign"}}))

            config, warning = load_config({}, local_path=path)

        self.assertIsNone(warning)
        self.assertEqual(config["campaign"]["default_name"], "AWS Campaign")
        self.assertEqual(config["geography"]["default_state"], "California")

    def test_s3_uri_loads_the_same_json_contract(self):
        client = FakeS3Client(json.dumps({"run_controls": {"persist_to_database": False}}))

        config, warning = load_config(
            {"STREAMLIT_CONFIG_S3_URI": "s3://config-bucket/apps/lead-source/config.json"},
            s3_client=client,
        )

        self.assertIsNone(warning)
        self.assertFalse(config["run_controls"]["persist_to_database"])
        self.assertEqual(
            client.request,
            {"Bucket": "config-bucket", "Key": "apps/lead-source/config.json"},
        )

    def test_dynamic_states_and_providers_can_be_added(self):
        client = FakeS3Client(json.dumps({
            "geography": {"state_areas": {"Washington": ["Seattle", "Tacoma"]}},
            "run_controls": {"provider_labels": {"New Directory": "new_directory"}},
        }))

        config, warning = load_config(
            {"STREAMLIT_CONFIG_S3_URI": "s3://config-bucket/config.json"},
            s3_client=client,
        )

        self.assertIsNone(warning)
        self.assertEqual(config["geography"]["state_areas"]["Washington"], ["Seattle", "Tacoma"])
        self.assertEqual(config["run_controls"]["provider_labels"]["New Directory"], "new_directory")

    def test_invalid_json_falls_back_to_defaults(self):
        client = FakeS3Client(b"not-json")

        config, warning = load_config(
            {"STREAMLIT_CONFIG_S3_URI": "s3://config-bucket/config.json"},
            s3_client=client,
        )

        self.assertIsNotNone(warning)
        self.assertEqual(config["campaign"]["default_name"], "California Small Business Discovery")

    def test_missing_file_falls_back_to_defaults(self):
        config, warning = load_config({}, local_path=Path("does-not-exist.json"))

        self.assertIsNotNone(warning)
        self.assertTrue(config["run_controls"]["persist_to_database"])

    def test_invalid_control_range_falls_back_to_defaults(self):
        client = FakeS3Client(json.dumps({
            "run_controls": {"lead_count": {"min": 10, "max": 20, "default": 5}}
        }))

        config, warning = load_config(
            {"STREAMLIT_CONFIG_S3_URI": "s3://config-bucket/config.json"},
            s3_client=client,
        )

        self.assertIsNotNone(warning)
        self.assertEqual(config["run_controls"]["lead_count"]["default"], 10)


if __name__ == "__main__":
    unittest.main()
