"""Load non-secret Streamlit configuration from S3 or the bundled JSON file."""

from __future__ import annotations

from copy import deepcopy
import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
CONFIG_S3_URI_ENV = "STREAMLIT_CONFIG_S3_URI"
CONFIG_FILE_ENV = "STREAMLIT_CONFIG_FILE"
DEFAULT_CONFIG_PATH = Path(__file__).with_name("streamlit_config.json")


def _read_json_bytes(raw: bytes | str) -> dict[str, Any]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("configuration root must be a JSON object")
    return parsed


def _read_s3(uri: str, s3_client=None) -> dict[str, Any]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError(f"{CONFIG_S3_URI_ENV} must use s3://bucket/key format")
    if s3_client is None:
        import boto3

        s3_client = boto3.client("s3")
    response = s3_client.get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
    return _read_json_bytes(response["Body"].read())


def _validate_shape(value: Any, template: Any, path: str = "config") -> None:
    if path == "config.geography.state_areas":
        if not isinstance(value, dict) or not all(
            isinstance(key, str)
            and isinstance(areas, list)
            and all(isinstance(area, str) for area in areas)
            for key, areas in value.items()
        ):
            raise ValueError(f"{path} must map state names to lists of areas")
        return
    if path == "config.run_controls.provider_labels":
        if not isinstance(value, dict) or not all(
            isinstance(label, str) and isinstance(provider, str)
            for label, provider in value.items()
        ):
            raise ValueError(f"{path} must map labels to provider names")
        return
    if isinstance(template, dict):
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
        for key, child in value.items():
            if key not in template:
                raise ValueError(f"unknown configuration key: {path}.{key}")
            _validate_shape(child, template[key], f"{path}.{key}")
    elif isinstance(template, list):
        if not isinstance(value, list):
            raise ValueError(f"{path} must be list")
        if template:
            for index, child in enumerate(value):
                _validate_shape(child, template[0], f"{path}[{index}]")
    elif type(value) is not type(template):
        raise ValueError(f"{path} must be {type(template).__name__}")


def _merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _validate_semantics(config: dict[str, Any]) -> None:
    geography = config["geography"]
    run = config["run_controls"]
    campaign = config["campaign"]
    if geography["default_country"] not in geography["countries"]:
        raise ValueError("default_country must be present in countries")
    if geography["default_state"] not in geography["us_states"]:
        raise ValueError("default_state must be present in us_states")
    if campaign["default_status"] not in campaign["statuses"]:
        raise ValueError("default_status must be present in statuses")
    if run["default_pipeline_version"] not in run["pipeline_versions"]:
        raise ValueError("default_pipeline_version must be present in pipeline_versions")
    if run["v2_pipeline_version"] not in run["pipeline_versions"]:
        raise ValueError("v2_pipeline_version must be present in pipeline_versions")
    if not set(run["default_providers"]).issubset(run["provider_labels"]):
        raise ValueError("default_providers must be present in provider_labels")
    for key in (
        "source_count_v1", "source_count_v2", "lead_count", "oversampling_factor",
        "max_queries", "results_per_query", "max_pages_per_query",
        "enrichment_batch_size",
    ):
        control = run[key]
        if not control["min"] <= control["default"] <= control["max"]:
            raise ValueError(f"{key}.default must be between min and max")


def load_config(
    environ: Optional[Mapping[str, str]] = None,
    *,
    local_path: Optional[Path] = None,
    s3_client=None,
) -> tuple[dict[str, Any], Optional[str]]:
    """Return validated configuration and an optional fallback warning."""
    env = os.environ if environ is None else environ
    try:
        defaults = _read_json_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"Bundled default configuration is invalid: {exc}") from exc

    uri = env.get(CONFIG_S3_URI_ENV, "").strip()
    configured_path = env.get(CONFIG_FILE_ENV, "").strip()
    source = uri or configured_path or str(local_path or DEFAULT_CONFIG_PATH)
    try:
        if uri:
            overrides = _read_s3(uri, s3_client)
        else:
            path = Path(configured_path) if configured_path else (local_path or DEFAULT_CONFIG_PATH)
            overrides = _read_json_bytes(path.read_bytes())
        _validate_shape(overrides, defaults)
        merged = _merge(defaults, overrides)
        _validate_semantics(merged)
        return merged, None
    except Exception as exc:
        warning = f"Could not load Streamlit configuration from {source}; using defaults ({type(exc).__name__})."
        logger.warning(warning)
        return defaults, warning
