"""Tests for compiling entities into prototype dictionaries."""

from typing import Any

from evennia.prototypes.spawner import spawn
from evennia.utils.test_resources import BaseEvenniaTestCase

from evennia_mudification import proto
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


class TestPrototypeTemplates(BaseEvenniaTestCase):
    def test_registration_makes_template_spawnable(self) -> None:
        from evennia_mudification.proto import register_prototypes

        index = _index_from(
            {
                "schema_version": 1,
                "entities": [
                    {
                        "id": "tpl",
                        "kind": "prototype",
                        "key": "goblin template",
                        "typeclass": "evennia.objects.objects.DefaultObject",
                        "attrs": {"hp": 5},
                    }
                ],
            }
        )
        assert register_prototypes(index) == 1
        (obj,) = spawn("tpl")
        assert obj.db.hp == 5
        obj.delete()

    def test_registration_without_templates_is_a_noop(self) -> None:
        from evennia_mudification.proto import register_prototypes

        index = _index_from(
            {
                "schema_version": 1,
                "entities": [{"id": "a", "kind": "room", "key": "a"}],
            }
        )
        assert register_prototypes(index) == 0

    def test_child_object_inherits_template_values(self) -> None:
        from evennia_mudification.proto import register_prototypes

        index = _index_from(
            {
                "schema_version": 1,
                "entities": [
                    {
                        "id": "tpl",
                        "kind": "prototype",
                        "key": "goblin template",
                        "typeclass": "evennia.objects.objects.DefaultObject",
                        "attrs": {"hp": 5},
                    },
                    {
                        "id": "guard",
                        "kind": "object",
                        "key": "a guard",
                        "prototype": "@tpl",
                    },
                ],
            }
        )
        register_prototypes(index)
        prototype = entity_to_prototype(
            index.entities["guard"], index=index, resolve_ref=_resolver
        )
        assert prototype["prototype_parent"] == "tpl"
        assert "typeclass" not in prototype  # the template supplies it
        (obj,) = spawn(prototype)
        assert obj.db.hp == 5
        # The template's engine tags must not leak onto the child.
        live_tags = obj.tags.all(return_key_and_category=True)
        assert ("tpl", ENTITY_TAG_CATEGORY) not in live_tags
        assert ("guard", ENTITY_TAG_CATEGORY) in live_tags
        obj.delete()

    def test_declared_typeclass_wins_over_template(self) -> None:
        index = _index_from(
            {
                "schema_version": 1,
                "entities": [
                    {"id": "tpl", "kind": "prototype", "key": "tpl"},
                    {
                        "id": "guard",
                        "kind": "object",
                        "key": "a guard",
                        "prototype": "@tpl",
                        "typeclass": "evennia.objects.objects.DefaultCharacter",
                    },
                ],
            }
        )
        prototype = entity_to_prototype(
            index.entities["guard"], index=index, resolve_ref=_resolver
        )
        assert prototype["typeclass"] == "evennia.objects.objects.DefaultCharacter"


class TestTemplateRegistry(BaseEvenniaTestCase):
    """The module-prototype namespace the engine registers into."""

    def _snapshot_registry(self) -> None:
        from evennia.prototypes.prototypes import _MODULE_PROTOTYPES

        originals = dict(_MODULE_PROTOTYPES)
        original_keys = set(proto._REGISTERED_KEYS)

        def restore() -> None:
            _MODULE_PROTOTYPES.clear()
            _MODULE_PROTOTYPES.update(originals)
            proto._REGISTERED_KEYS.clear()
            proto._REGISTERED_KEYS.update(original_keys)

        self.addCleanup(restore)

    def _template_index(self, *, hp: int = 5) -> ContentIndex:
        return _index_from(
            {
                "schema_version": 1,
                "entities": [
                    {
                        "id": "tpl",
                        "kind": "prototype",
                        "key": "goblin template",
                        "typeclass": "evennia.objects.objects.DefaultObject",
                        "attrs": {"hp": hp},
                    }
                ],
            }
        )

    def test_collision_with_a_game_prototype_is_refused(self) -> None:
        from evennia.prototypes.prototypes import (
            load_module_prototypes,
            search_prototype,
        )

        from evennia_mudification.proto import register_prototypes

        self._snapshot_registry()
        load_module_prototypes({"prototype_key": "tpl", "key": "GAME TEMPLATE"})

        assert register_prototypes(self._template_index()) == 0
        (found,) = search_prototype("tpl", no_db=True)
        assert found["key"] == "GAME TEMPLATE"
        assert proto.registered_keys() == frozenset()

    def test_engine_templates_refresh_without_self_collision(self) -> None:
        from evennia.prototypes.prototypes import search_prototype

        from evennia_mudification.proto import register_prototypes

        self._snapshot_registry()
        assert register_prototypes(self._template_index(hp=5)) == 1
        assert register_prototypes(self._template_index(hp=7)) == 1
        (found,) = search_prototype("tpl", no_db=True)
        attrs = {entry[0]: entry[1] for entry in found["attrs"]}
        assert attrs["hp"] == 7
        assert proto.registered_keys() == frozenset({"tpl"})

    def test_undeclared_templates_are_deregistered(self) -> None:
        from evennia.prototypes.prototypes import search_prototype

        from evennia_mudification.proto import register_prototypes

        self._snapshot_registry()
        assert register_prototypes(self._template_index()) == 1
        no_templates = _index_from(
            {
                "schema_version": 1,
                "entities": [{"id": "a", "kind": "room", "key": "a"}],
            }
        )
        assert register_prototypes(no_templates) == 0
        assert search_prototype("tpl", no_db=True) == []
        assert proto.registered_keys() == frozenset()


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
