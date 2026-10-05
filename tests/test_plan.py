"""Tests for planning against the live database."""

import tempfile
from pathlib import Path
from typing import Any

import pytest
from evennia.prototypes.spawner import spawn
from evennia.utils import create
from evennia.utils.test_resources import BaseEvenniaTestCase

from evennia_mudification.apply import apply_plan
from evennia_mudification.compile import ContentIndex, compile_documents
from evennia_mudification.identity import ENTITY_TAG_CATEGORY
from evennia_mudification.plan import Plan, UnsupportedEntityError, build_plan
from evennia_mudification.proto import entity_to_prototype
from evennia_mudification.source import LocalDirectorySource

CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "basic"


class TestPlan(BaseEvenniaTestCase):
    def _index(self, root: Path = CORPUS) -> ContentIndex:
        return compile_documents(LocalDirectorySource(root).documents())

    def _resolver(self, ref: str) -> Any:
        obj = self._find(ref)
        assert obj is not None, ref
        return obj

    def _find(self, ref: str) -> Any:
        from evennia_mudification.identity import find_entity_object
        from evennia_mudification.models import ref_target

        return find_entity_object(ref_target(ref))

    def test_first_plan_creates_everything(self) -> None:
        plan = build_plan(self._index(), resolve_ref=self._resolver)
        assert {change.entity_id for change in plan.changes} == {
            "square",
            "inn",
            "square-inn",
            "signpost",
        }
        assert all(change.action == "create" for change in plan.changes)
        assert plan.retirements == set()

    def test_extra_managed_object_is_retired(self) -> None:
        create.create_object(
            "evennia.objects.objects.DefaultObject",
            key="rogue",
            tags=[("rogue", ENTITY_TAG_CATEGORY)],
        )
        plan = build_plan(self._index(), resolve_ref=self._resolver)
        assert plan.retirements == {"rogue"}

    def test_prototype_entities_are_unsupported(self) -> None:
        # tmp_path cannot be injected into a unittest.TestCase method; an
        # absolute scratch directory is what the brief's tmp_path stood for.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "c.yaml").write_text(
                "schema_version: 1\nentities:\n"
                "  - id: tpl\n    kind: prototype\n    key: tpl\n"
            )
            with pytest.raises(UnsupportedEntityError):
                build_plan(self._index(root), resolve_ref=self._resolver)

    def test_render_lists_creates(self) -> None:
        plan = build_plan(self._index(), resolve_ref=self._resolver)
        assert "create square" in plan.render()

    def test_existing_object_is_updated_and_rogue_retired(self) -> None:
        create.create_object(
            "evennia.objects.objects.DefaultRoom",
            key="stale square",
            tags=[("square", ENTITY_TAG_CATEGORY)],
        )
        create.create_object(
            "evennia.objects.objects.DefaultObject",
            key="rogue",
            tags=[("rogue", ENTITY_TAG_CATEGORY)],
        )
        plan = build_plan(self._index(), resolve_ref=self._resolver)
        updates = [change for change in plan.changes if change.action == "update"]
        assert [change.entity_id for change in updates] == ["square"]
        assert "key" in updates[0].diff
        assert updates[0].render().startswith("update square: ")
        assert "retire rogue (reported only)" in plan.render()
        assert not plan.is_empty()

    def test_empty_plan_renders_no_changes(self) -> None:
        plan = Plan()
        assert plan.is_empty()
        assert plan.render() == "no changes"

    def test_matching_object_yields_no_change(self) -> None:
        index = self._index()
        prototype = entity_to_prototype(
            index.entities["square"], index=index, resolve_ref=self._resolver
        )
        spawn(prototype)
        plan = build_plan(self._index(), resolve_ref=self._resolver)
        assert "square" not in {change.entity_id for change in plan.changes}
        # Only the three not-yet-created entities remain.
        assert not plan.is_empty()
        assert {change.entity_id for change in plan.changes} == {
            "inn",
            "square-inn",
            "signpost",
        }

    def test_matching_child_object_yields_no_change(self) -> None:
        index = self._index()
        for entity_id in ("square", "signpost"):
            prototype = entity_to_prototype(
                index.entities[entity_id], index=index, resolve_ref=self._resolver
            )
            spawn(prototype)
        plan = build_plan(self._index(), resolve_ref=self._resolver)
        entity_ids = {change.entity_id for change in plan.changes}
        assert "square" not in entity_ids
        assert "signpost" not in entity_ids

    def test_builder_state_is_not_a_change(self) -> None:
        index = self._index()
        prototype = entity_to_prototype(
            index.entities["inn"], index=index, resolve_ref=self._resolver
        )
        inn = spawn(prototype)[0]
        inn.db.notes = "builder scribbles"
        inn.aliases.add("tavern")
        plan = build_plan(self._index(), resolve_ref=self._resolver)
        assert "inn" not in {change.entity_id for change in plan.changes}

    def test_declared_locks_and_mixed_case_permissions_stay_idempotent(self) -> None:
        # A unittest.TestCase cannot take pytest's tmp_path fixture; the temp
        # directory stands in for a content checkout.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = root / "hall.yaml"
            content.write_text(
                "schema_version: 1\nentities:\n"
                "  - id: hall\n    kind: room\n    key: The hall\n"
                '    locks:\n      get: "false()"\n'
                "    permissions:\n      - Builders\n",
                encoding="utf-8",
            )
            index = self._index(root)
            prototype = entity_to_prototype(
                index.entities["hall"], index=index, resolve_ref=self._resolver
            )
            hall = spawn(prototype)[0]
            assert "get:false()" in hall.locks.all()
            assert "builders" in hall.permissions.all()

            # Evennia stores the full default lockset and lowercased
            # permissions; declared-subset comparison must see no change.
            assert build_plan(self._index(root), resolve_ref=self._resolver).is_empty()

            # A real update is still reported and, once applied, converges
            # back to an empty plan.
            content.write_text(
                content.read_text(encoding="utf-8").replace(
                    "The hall", "The great hall"
                ),
                encoding="utf-8",
            )
            index2 = self._index(root)
            plan = build_plan(index2, resolve_ref=self._resolver)
            assert [change.entity_id for change in plan.changes] == ["hall"]
            assert set(plan.changes[0].diff) == {"key"}
            assert apply_plan(plan, index=index2, resolve_ref=self._resolver).ok
            assert build_plan(self._index(root), resolve_ref=self._resolver).is_empty()

            # A declared lock the object does not have is a real change.
            content.write_text(
                content.read_text(encoding="utf-8").replace("false()", "true()"),
                encoding="utf-8",
            )
            index3 = self._index(root)
            plan3 = build_plan(index3, resolve_ref=self._resolver)
            assert [change.entity_id for change in plan3.changes] == ["hall"]
            assert set(plan3.changes[0].diff) == {"locks"}
            assert apply_plan(plan3, index=index3, resolve_ref=self._resolver).ok
            assert "get:true()" in hall.locks.all()
            assert build_plan(self._index(root), resolve_ref=self._resolver).is_empty()

            # A declared permission the object does not have is also a real
            # change, added case-insensitively.
            content.write_text(
                content.read_text(encoding="utf-8").replace(
                    "- Builders", "- Builders\n      - Admins"
                ),
                encoding="utf-8",
            )
            index4 = self._index(root)
            plan4 = build_plan(index4, resolve_ref=self._resolver)
            assert [change.entity_id for change in plan4.changes] == ["hall"]
            assert set(plan4.changes[0].diff) == {"permissions"}
            assert apply_plan(plan4, index=index4, resolve_ref=self._resolver).ok
            assert "admins" in hall.permissions.all()
            assert build_plan(self._index(root), resolve_ref=self._resolver).is_empty()
