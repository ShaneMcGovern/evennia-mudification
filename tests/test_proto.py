"""Tests for compiling entities into prototype dictionaries."""

from typing import Any

from evennia.prototypes.spawner import spawn
from evennia.utils.test_resources import BaseEvenniaTestCase

from evennia_mudification.compile import ContentIndex
from evennia_mudification.identity import ENTITY_TAG_CATEGORY, SOURCE_TAG_CATEGORY
from evennia_mudification.models import Bundle
from evennia_mudification.proto import entity_to_prototype


def _index_from(raw: dict[str, Any]) -> ContentIndex:
    bundle = Bundle.model_validate(raw)
    return ContentIndex(
        entities={entity.id: entity for entity in bundle.entities},
        entity_sources={entity.id: "village.yaml" for entity in bundle.entities},
        sources=["village.yaml"],
    )


def _resolver(ref: str) -> Any:
    return {"ref": ref}


class TestProto(BaseEvenniaTestCase):
    def test_room_defaults_and_tags(self) -> None:
        index = _index_from(
            {
                "schema_version": 1,
                "entities": [{"id": "square", "kind": "room", "key": "The square"}],
            }
        )
        prototype = entity_to_prototype(
            index.entities["square"], index=index, resolve_ref=_resolver
        )
        assert prototype["prototype_key"] == "square"
        assert prototype["typeclass"] == "evennia.objects.objects.DefaultRoom"
        assert ("square", ENTITY_TAG_CATEGORY) in prototype["tags"]
        assert ("village.yaml", SOURCE_TAG_CATEGORY) in prototype["tags"]

    def test_exit_resolves_refs_and_locks(self) -> None:
        index = _index_from(
            {
                "schema_version": 1,
                "entities": [
                    {"id": "a", "kind": "room", "key": "a"},
                    {"id": "b", "kind": "room", "key": "b"},
                    {
                        "id": "door",
                        "kind": "exit",
                        "key": "door",
                        "location": "@a",
                        "destination": "@b",
                        "locks": {"get": "false()"},
                    },
                ],
            }
        )
        prototype = entity_to_prototype(
            index.entities["door"], index=index, resolve_ref=_resolver
        )
        assert prototype["location"] == {"ref": "@a"}
        assert prototype["destination"] == {"ref": "@b"}
        assert prototype["locks"] == "get:false()"

    def test_desc_becomes_attr(self) -> None:
        index = _index_from(
            {
                "schema_version": 1,
                "entities": [{"id": "a", "kind": "room", "key": "a", "desc": "hi"}],
            }
        )
        prototype = entity_to_prototype(
            index.entities["a"], index=index, resolve_ref=_resolver
        )
        assert ("desc", "hi") in prototype["attrs"]

    def test_desc_attr_survives_spawn(self) -> None:
        index = _index_from(
            {
                "schema_version": 1,
                "entities": [{"id": "a", "kind": "room", "key": "a", "desc": "hi"}],
            }
        )
        prototype = entity_to_prototype(
            index.entities["a"], index=index, resolve_ref=_resolver
        )
        obj = spawn(prototype)[0]
        assert obj.db.desc == "hi"
        obj.delete()

    def test_object_resolves_location_and_home(self) -> None:
        index = _index_from(
            {
                "schema_version": 1,
                "entities": [
                    {"id": "inn", "kind": "room", "key": "inn"},
                    {
                        "id": "sword",
                        "kind": "object",
                        "key": "sword",
                        "location": "@inn",
                        "home": "@inn",
                    },
                ],
            }
        )
        prototype = entity_to_prototype(
            index.entities["sword"], index=index, resolve_ref=_resolver
        )
        assert prototype["typeclass"] == "evennia.objects.objects.DefaultObject"
        assert prototype["location"] == {"ref": "@inn"}
        assert prototype["home"] == {"ref": "@inn"}

    def test_object_without_location_or_home_omits_keys(self) -> None:
        index = _index_from(
            {
                "schema_version": 1,
                "entities": [{"id": "sword", "kind": "object", "key": "sword"}],
            }
        )
        prototype = entity_to_prototype(
            index.entities["sword"], index=index, resolve_ref=_resolver
        )
        assert "location" not in prototype
        assert "home" not in prototype

    def test_declared_locks_and_permissions_are_kept(self) -> None:
        index = _index_from(
            {
                "schema_version": 1,
                "entities": [
                    {
                        "id": "a",
                        "kind": "room",
                        "key": "a",
                        "locks": {"get": "false()"},
                        "permissions": ["Builders"],
                    }
                ],
            }
        )
        prototype = entity_to_prototype(
            index.entities["a"], index=index, resolve_ref=_resolver
        )
        assert prototype["locks"] == "get:false()"
        assert prototype["permissions"] == ["Builders"]

    def test_declared_aliases_are_kept(self) -> None:
        index = _index_from(
            {
                "schema_version": 1,
                "entities": [
                    {"id": "a", "kind": "room", "key": "a", "aliases": ["b", "c"]}
                ],
            }
        )
        prototype = entity_to_prototype(
            index.entities["a"], index=index, resolve_ref=_resolver
        )
        assert prototype["aliases"] == ["b", "c"]

    def test_empty_declarations_are_omitted(self) -> None:
        index = _index_from(
            {
                "schema_version": 1,
                "entities": [{"id": "a", "kind": "room", "key": "a"}],
            }
        )
        prototype = entity_to_prototype(
            index.entities["a"], index=index, resolve_ref=_resolver
        )
        assert "aliases" not in prototype
        assert "attrs" not in prototype
        assert "locks" not in prototype
        assert "permissions" not in prototype
