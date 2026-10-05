"""Tests for the content models."""

import pytest
import yaml
from pydantic import ValidationError

from evennia_mudification.models import Bundle, RoomEntity, ref_target

VALID = {
    "schema_version": 1,
    "zone": "village",
    "entities": [
        {"id": "square", "kind": "room", "key": "The village square"},
        {"id": "inn", "kind": "room", "key": "The inn"},
        {
            "id": "square-inn",
            "kind": "exit",
            "key": "inn door",
            "location": "@square",
            "destination": "@inn",
        },
        {
            "id": "signpost",
            "kind": "object",
            "key": "a signpost",
            "location": "@square",
        },
        {"id": "villager", "kind": "prototype", "key": "a villager"},
    ],
}


def test_valid_bundle_parses() -> None:
    bundle = Bundle.model_validate(VALID)
    assert isinstance(bundle.entities[0], RoomEntity)
    assert {entity.id for entity in bundle.entities} == {
        "square",
        "inn",
        "square-inn",
        "signpost",
        "villager",
    }


def test_ref_target_strips_at() -> None:
    assert ref_target("@square") == "square"


def test_unknown_field_rejected() -> None:
    bad = {
        "schema_version": 1,
        "entities": [{"id": "square", "kind": "room", "key": "x", "locaton": "@inn"}],
    }
    with pytest.raises(ValidationError) as error:
        Bundle.model_validate(bad)
    assert "locaton" in str(error.value)


def test_non_string_key_rejected_after_yaml_load() -> None:
    document = (
        "schema_version: 1\nentities:\n  - id: square\n    kind: room\n    key: no\n"
    )
    raw = yaml.safe_load(document)
    assert raw["entities"][0]["key"] is False  # YAML 1.1 boolean
    with pytest.raises(ValidationError):
        Bundle.model_validate(raw)


def test_ids_must_be_lowercase_slugs() -> None:
    bad = {
        "schema_version": 1,
        "entities": [{"id": "Square", "kind": "room", "key": "x"}],
    }
    with pytest.raises(ValidationError):
        Bundle.model_validate(bad)


def test_refs_must_start_with_at() -> None:
    bad = {
        "schema_version": 1,
        "entities": [
            {"id": "a", "kind": "room", "key": "a"},
            {
                "id": "b",
                "kind": "exit",
                "key": "b",
                "location": "a",
                "destination": "@a",
            },
        ],
    }
    with pytest.raises(ValidationError):
        Bundle.model_validate(bad)


def test_exit_requires_location_and_destination() -> None:
    bad = {"schema_version": 1, "entities": [{"id": "b", "kind": "exit", "key": "b"}]}
    with pytest.raises(ValidationError):
        Bundle.model_validate(bad)


def test_unsupported_schema_version_rejected() -> None:
    bad = {"schema_version": 99, "entities": []}
    with pytest.raises(ValidationError):
        Bundle.model_validate(bad)
