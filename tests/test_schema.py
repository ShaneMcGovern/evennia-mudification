"""Tests for the generated JSON Schema artifact."""

import json
from pathlib import Path

from evennia_mudification.schema import generate_json_schema, write_schema

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "schema" / "mudification.schema.json"


def test_generated_schema_matches_committed_artifact() -> None:
    assert json.loads(ARTIFACT.read_text(encoding="utf-8")) == generate_json_schema()


def test_schema_forbids_unknown_fields() -> None:
    schema = generate_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_write_schema_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "mudification.schema.json"
    write_schema(target)
    assert json.loads(target.read_text(encoding="utf-8")) == generate_json_schema()


def test_schema_pins_the_supported_version() -> None:
    schema = generate_json_schema()
    assert schema["properties"]["schema_version"]["const"] == 1


def test_zone_is_described_in_the_schema() -> None:
    schema = generate_json_schema()
    assert "description" in schema["properties"]["zone"]
