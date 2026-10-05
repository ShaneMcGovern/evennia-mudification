"""Generate the JSON Schema artifact published for editors and CI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evennia_mudification.models import Bundle

SCHEMA_PATH = Path("schema/mudification.schema.json")


def generate_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for content bundles."""
    schema = Bundle.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Mudification content bundle"
    return schema


def write_schema(path: Path = SCHEMA_PATH) -> None:
    """Write the schema artifact to `path`, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(generate_json_schema(), indent=2) + "\n", encoding="utf-8"
    )
