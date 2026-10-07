"""Tests for planning against the live database."""

import shutil
import tempfile
from pathlib import Path
from typing import Any

from evennia.prototypes.spawner import spawn
from evennia.utils import create
from evennia.utils.test_resources import BaseEvenniaTestCase

from evennia_mudification.apply import apply_plan
from evennia_mudification.compile import ContentIndex, compile_documents
from evennia_mudification.identity import ENTITY_TAG_CATEGORY, SOURCE_TAG_CATEGORY
from evennia_mudification.plan import Plan, build_plan
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
            tags=[
                ("rogue", ENTITY_TAG_CATEGORY),
                ("village.yaml", SOURCE_TAG_CATEGORY),
            ],
        )
        plan = build_plan(self._index(), resolve_ref=self._resolver)
        assert plan.retirements == {"rogue"}

    def test_duplicate_managed_objects_are_surfaced(self) -> None:
        for _ in range(2):
            create.create_object(
                "evennia.objects.objects.DefaultRoom",
                key="stale square",
                tags=[
                    ("square", ENTITY_TAG_CATEGORY),
                    ("village.yaml", SOURCE_TAG_CATEGORY),
                ],
            )
        plan = build_plan(self._index(), resolve_ref=self._resolver)
        assert plan.duplicates == {"square": 2}
        assert "duplicate square: 2 live objects" in plan.render()

    def test_prototype_entities_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "c.yaml").write_text(
                "schema_version: 1\nentities:\n"
                "  - id: tpl\n    kind: prototype\n    key: tpl\n"
                "  - id: room\n    kind: room\n    key: room\n"
            )
            plan = build_plan(self._index(root), resolve_ref=self._resolver)
        assert {change.entity_id for change in plan.changes} == {"room"}
        assert plan.retirements == set()

    def test_ref_to_declared_unapplied_entity_plans_an_update(self) -> None:
        # Planning resolves refs for existing objects; a target declared in
        # the same edit has no live object yet, and the create pass makes it
        # available before the update phase runs.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "basic"
            shutil.copytree(CORPUS, root)
            index = self._index(root)
            assert apply_plan(
                build_plan(index, resolve_ref=self._resolver),
                index=index,
                resolve_ref=self._resolver,
            ).ok

            corpus_file = root / "village.yaml"
            text = corpus_file.read_text(encoding="utf-8")
            text = text.replace(
                'key: a wooden signpost\n    location: "@square"',
                'key: a wooden signpost\n    location: "@attic"',
            )
            corpus_file.write_text(
                text.rstrip("\n")
                + "\n  - id: attic\n    kind: room\n    key: a dusty attic\n",
                encoding="utf-8",
            )

            def lookup_only(ref: str) -> Any:
                obj = self._find(ref)
                if obj is None:
                    raise LookupError(f"reference '{ref}' has not been applied yet")
                return obj

            index2 = self._index(root)
            plan = build_plan(index2, resolve_ref=lookup_only)
            updates = [change for change in plan.changes if change.action == "update"]
            assert [change.entity_id for change in updates] == ["signpost"]
            assert set(updates[0].diff) == {"location"}
            assert "create attic" in plan.render()

            report = apply_plan(plan, index=index2, resolve_ref=self._resolver)
            assert report.ok
            assert self._find("@signpost").location == self._find("@attic")

    def test_render_lists_creates(self) -> None:
        plan = build_plan(self._index(), resolve_ref=self._resolver)
        assert "create square" in plan.render()

    def test_existing_object_is_updated_and_rogue_retired(self) -> None:
        create.create_object(
            "evennia.objects.objects.DefaultRoom",
            key="stale square",
            tags=[
                ("square", ENTITY_TAG_CATEGORY),
                ("village.yaml", SOURCE_TAG_CATEGORY),
            ],
        )
        create.create_object(
            "evennia.objects.objects.DefaultObject",
            key="rogue",
            tags=[
                ("rogue", ENTITY_TAG_CATEGORY),
                ("village.yaml", SOURCE_TAG_CATEGORY),
            ],
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
        # unittest.TestCase cannot take pytest's tmp_path fixture; tempfile stands in.
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

            # Evennia stores the full lockset and lowercased permissions;
            # subset comparison must see no change.
            assert build_plan(self._index(root), resolve_ref=self._resolver).is_empty()

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

    def test_mixed_case_aliases_tags_and_padded_permissions_stay_idempotent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "hall.yaml").write_text(
                "schema_version: 1\nentities:\n"
                "  - id: hall\n    kind: room\n    key: The hall\n"
                "    aliases: [Hall, GREAT-HALL]\n"
                "    permissions:\n      - ' Builders '\n"
                "    tags:\n      Great: Zone\n",
                encoding="utf-8",
            )
            index = self._index(root)
            plan = build_plan(index, resolve_ref=self._resolver)
            assert apply_plan(plan, index=index, resolve_ref=self._resolver).ok
            # Evennia stored these stripped and lowercased; subset comparison
            # must see no change.
            assert build_plan(self._index(root), resolve_ref=self._resolver).is_empty()

    def test_changed_alias_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = root / "hall.yaml"
            content.write_text(
                "schema_version: 1\nentities:\n"
                "  - id: hall\n    kind: room\n    key: The hall\n"
                "    aliases: [great-hall]\n",
                encoding="utf-8",
            )
            index = self._index(root)
            assert apply_plan(
                build_plan(index, resolve_ref=self._resolver),
                index=index,
                resolve_ref=self._resolver,
            ).ok

            content.write_text(
                "schema_version: 1\nentities:\n"
                "  - id: hall\n    kind: room\n    key: The hall\n"
                "    aliases: [great-hall, throne-room]\n",
                encoding="utf-8",
            )
            index2 = self._index(root)
            plan = build_plan(index2, resolve_ref=self._resolver)
            assert [change.entity_id for change in plan.changes] == ["hall"]
            assert set(plan.changes[0].diff) == {"aliases"}
            assert apply_plan(plan, index=index2, resolve_ref=self._resolver).ok
            assert build_plan(self._index(root), resolve_ref=self._resolver).is_empty()

    def test_changed_declared_tag_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = root / "hall.yaml"
            content.write_text(
                "schema_version: 1\nentities:\n"
                "  - id: hall\n    kind: room\n    key: The hall\n"
                "    tags:\n      Great: Zone\n",
                encoding="utf-8",
            )
            index = self._index(root)
            assert apply_plan(
                build_plan(index, resolve_ref=self._resolver),
                index=index,
                resolve_ref=self._resolver,
            ).ok

            content.write_text(
                "schema_version: 1\nentities:\n"
                "  - id: hall\n    kind: room\n    key: The hall\n"
                "    tags:\n      Great: Zone\n      Throne: Zone\n",
                encoding="utf-8",
            )
            index2 = self._index(root)
            plan = build_plan(index2, resolve_ref=self._resolver)
            assert [change.entity_id for change in plan.changes] == ["hall"]
            assert set(plan.changes[0].diff) == {"tags"}
            assert apply_plan(plan, index=index2, resolve_ref=self._resolver).ok
            assert build_plan(self._index(root), resolve_ref=self._resolver).is_empty()
