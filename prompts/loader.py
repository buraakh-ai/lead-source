from pathlib import Path
from typing import Any, Dict

import yaml

_PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompt(name: str, **fmt: Any) -> Dict[str, Any]:
    """Load a prompt YAML file by name (without the .yaml extension).

    Any {placeholder} in an instruction line is filled in from `fmt` (e.g.
    source_count, lead_count) so runtime values never need to live in Python.
    """
    path = _PROMPTS_DIR / f"{name}.yaml"
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if fmt:
        data["instructions"] = [line.format(**fmt) for line in data["instructions"]]

    return data
