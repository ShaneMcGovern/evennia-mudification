"""Tests for applying a plan."""

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

from evennia.prototypes import spawner
from evennia.utils.test_resources import BaseEvenniaTestCase

from evennia_mudification import apply as apply_module
from evennia_mudification import proto
from evennia_mudification.apply import apply_plan
from evennia_mudification.compile import ContentIndex, compile_documents
from evennia_mudification.identity import find_entity_object
from evennia_mudification.models import EntityBase, ref_target
from evennia_mudification.plan import build_plan
from evennia_mudification.proto import (
    RefResolver,
    entity_to_prototype,
    register_prototypes,
)
from evennia_mudification.source import LocalDirectorySource

CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "basic"


class TestApply(BaseEvenniaTestCase):
    def _index(self, root: Path = CORPUS) -> ContentIndex:
        return compile_documents(LocalDirectorySource(root).documents())

    def _resolver(self, ref: str) -> Any:
        obj = find_entity_object(ref_target(ref))
        if obj is None:
            raise LookupError(f"reference '{ref}' has not been applied yet")
        return obj

    def test_apply_creates_and_is_idempotent(self) -> None:
        index = self._index()
        plan = build_plan(index, resolve_ref=self._resolver)
        report = apply_plan(plan, index=index, resolve_ref=self._resolver)
        assert report.ok
        assert find_entity_object("square") is not None

        second = build_plan(self._index(), resolve_ref=self._resolver)
        assert second.is_empty()
        second_report = apply_plan(
            second, index=self._index(), resolve_ref=self._resolver
        )
        assert second_report.ok
        assert second_report.render() == "nothing to apply"

    def test_failures_are_isolated(self) -> None:
        index = self._index()
        plan = build_plan(index, resolve_ref=self._resolver)
        original: Callable[..., dict[str, Any]] = entity_to_prototype

        def explode(
            entity: EntityBase, *, index: ContentIndex, resolve_ref: RefResolver
        ) -> dict[str, Any]:
            if entity.id == "signpost":
                raise RuntimeError("boom")
            return original(entity, index=index, resolve_ref=resolve_ref)

        # unittest.TestCase cannot take pytest's monkeypatch fixture; patch.object
        # is the equivalent context manager.
        with mock.patch.object(apply_module, "entity_to_prototype", explode):
            report = apply_plan(plan, index=index, resolve_ref=self._resolver)
        assert not report.ok
        failed = [result for result in report.results if not result.ok]
        assert [result.entity_id for result in failed] == ["signpost"]
        assert failed[0].error is not None
        assert "boom" in failed[0].error
        assert find_entity_object("square") is not None

    def test_object_in_object_placement_applies_in_one_run(self) -> None:
        # unittest.TestCase cannot take pytest's tmp_path fixture; tempfile
        # stands in. `coin` precedes `chest` and both are objects, so only a
        # retry pass can place it.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "c.yaml").write_text(
                "schema_version: 1\nentities:\n"
                "  - id: coin\n    kind: object\n    key: a gold coin\n"
                '    location: "@chest"\n'
                "  - id: chest\n    kind: object\n    key: a wooden chest\n"
                '    location: "@room"\n'
                "  - id: room\n    kind: room\n    key: a storeroom\n",
                encoding="utf-8",
            )
            index = self._index(root)
            plan = build_plan(index, resolve_ref=self._resolver)
            assert {
                change.entity_id for change in plan.changes if change.action == "create"
            } == {"coin", "chest", "room"}

            report = apply_plan(plan, index=index, resolve_ref=self._resolver)
            assert report.ok
            assert len(report.results) == 3
            coin = find_entity_object("coin")
            chest = find_entity_object("chest")
            assert coin is not None
            assert chest is not None
            assert coin.location == chest

    def test_unresolvable_ref_fails_after_retries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "c.yaml").write_text(
                "schema_version: 1\nentities:\n"
                "  - id: coin\n    kind: object\n    key: a gold coin\n"
                '    location: "@ghost"\n',
                encoding="utf-8",
            )
            index = self._index(root)
            plan = build_plan(index, resolve_ref=self._resolver)
            report = apply_plan(plan, index=index, resolve_ref=self._resolver)
            assert not report.ok
            assert len(report.results) == 1
            assert report.results[0].entity_id == "coin"
            assert "@ghost" in (report.results[0].error or "")

    def test_update_changes_existing_object(self) -> None:
        # unittest.TestCase cannot take pytest's tmp_path fixture; tempfile stands in.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "basic"
            shutil.copytree(CORPUS, root)

            index = self._index(root)
            plan = build_plan(index, resolve_ref=self._resolver)
            assert apply_plan(plan, index=index, resolve_ref=self._resolver).ok

            corpus_file = root / "village.yaml"
            text = corpus_file.read_text(encoding="utf-8")
            text = text.replace("A well-worn square.", "A busy market square.")
            text = text.replace("The Wayfarer's Inn", "The Weary Wayfarer")
            corpus_file.write_text(text, encoding="utf-8")

            index2 = self._index(root)
            plan2 = build_plan(index2, resolve_ref=self._resolver)
            assert {change.entity_id for change in plan2.changes} == {"square", "inn"}
            assert all(change.action == "update" for change in plan2.changes)

            report = apply_plan(plan2, index=index2, resolve_ref=self._resolver)
            assert report.ok
            assert "update inn" in report.render()

            square = find_entity_object("square")
            inn = find_entity_object("inn")
            assert square is not None
            assert inn is not None
            square.refresh_from_db()
            inn.refresh_from_db()
            assert square.db.desc == "A busy market square.\n"
            assert inn.key == "The Weary Wayfarer"

    def test_update_failure_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "basic"
            shutil.copytree(CORPUS, root)
            index = self._index(root)
            plan = build_plan(index, resolve_ref=self._resolver)
            assert apply_plan(plan, index=index, resolve_ref=self._resolver).ok

            corpus_file = root / "village.yaml"
            corpus_file.write_text(
                corpus_file.read_text(encoding="utf-8").replace(
                    "The Wayfarer's Inn", "The Weary Wayfarer"
                ),
                encoding="utf-8",
            )
            index2 = self._index(root)
            plan2 = build_plan(index2, resolve_ref=self._resolver)
            with mock.patch.object(
                spawner,
                "batch_update_objects_with_prototype",
                side_effect=RuntimeError("boom"),
            ):
                report = apply_plan(plan2, index=index2, resolve_ref=self._resolver)
            assert not report.ok
            failed = [result for result in report.results if not result.ok]
            assert [result.entity_id for result in failed] == ["inn"]
            assert failed[0].error is not None
            assert "boom" in failed[0].error

    def test_update_that_did_not_apply_is_reported_as_failure(self) -> None:
        # Evennia's batch update swallows per-key failures and still reports a
        # change, so the row must be verified against the object afterwards.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = root / "world.yaml"
            content.write_text(
                "schema_version: 1\nentities:\n"
                "  - id: relic\n    kind: object\n    key: a brass relic\n",
                encoding="utf-8",
            )
            index = self._index(root)
            plan = build_plan(index, resolve_ref=self._resolver)
            assert apply_plan(plan, index=index, resolve_ref=self._resolver).ok

            content.write_text(
                "schema_version: 1\nentities:\n"
                "  - id: relic\n    kind: object\n    key: a brass relic\n"
                '    attrs: {hp: "$protkey(missing)"}\n',
                encoding="utf-8",
            )
            index2 = self._index(root)
            plan2 = build_plan(index2, resolve_ref=self._resolver)
            assert [change.action for change in plan2.changes] == ["update"]

            report = apply_plan(plan2, index=index2, resolve_ref=self._resolver)
            relic = find_entity_object("relic")
            assert relic is not None
            assert relic.attributes.get("hp") is None
            assert not report.ok
            failed = [result for result in report.results if not result.ok]
            assert [result.entity_id for result in failed] == ["relic"]
            assert "attrs" in (failed[0].error or "")

    def test_update_of_vanished_object_reports_a_clear_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "basic"
            shutil.copytree(CORPUS, root)
            index = self._index(root)
            plan = build_plan(index, resolve_ref=self._resolver)
            assert apply_plan(plan, index=index, resolve_ref=self._resolver).ok

            corpus_file = root / "village.yaml"
            corpus_file.write_text(
                corpus_file.read_text(encoding="utf-8").replace(
                    "a wooden signpost", "a weathered signpost"
                ),
                encoding="utf-8",
            )
            index2 = self._index(root)
            plan2 = build_plan(index2, resolve_ref=self._resolver)
            assert [change.entity_id for change in plan2.changes] == ["signpost"]

            signpost = find_entity_object("signpost")
            assert signpost is not None
            signpost.delete()

            report = apply_plan(plan2, index=index2, resolve_ref=self._resolver)
            assert not report.ok
            failed = [result for result in report.results if not result.ok]
            assert [result.entity_id for result in failed] == ["signpost"]
            error = failed[0].error or ""
            assert "NoneType" not in error
            assert "re-run plan" in error


class TestTemplateUpdates(BaseEvenniaTestCase):
    def _index(self, root: Path) -> ContentIndex:
        return compile_documents(LocalDirectorySource(root).documents())

    def _resolver(self, ref: str) -> Any:
        obj = find_entity_object(ref_target(ref))
        if obj is None:
            raise LookupError(f"reference '{ref}' has not been applied yet")
        return obj

    def _snapshot_registry(self) -> None:
        from evennia.prototypes.prototypes import _MODULE_PROTOTYPES

        originals = dict(_MODULE_PROTOTYPES)
        # The engine's own key bookkeeping only exists once the registry fix
        # lands; tolerate its absence so these tests can run either way.
        keys = getattr(proto, "_REGISTERED_KEYS", None)
        original_keys: set[str] = set(keys) if keys is not None else set()

        def restore() -> None:
            _MODULE_PROTOTYPES.clear()
            _MODULE_PROTOTYPES.update(originals)
            if keys is not None:
                keys.clear()
                keys.update(original_keys)

        self.addCleanup(restore)

    def _write_content(self, root: Path, *, parent: str) -> None:
        (root / "c.yaml").write_text(
            "schema_version: 1\nentities:\n"
            "  - id: tpl\n    kind: prototype\n    key: tpl\n"
            "    typeclass: evennia.objects.objects.DefaultObject\n"
            "    attrs: {hp: 5}\n"
            "  - id: tpl2\n    kind: prototype\n    key: tpl2\n"
            "    typeclass: evennia.objects.objects.DefaultObject\n"
            "    attrs: {hp: 9}\n"
            "  - id: guard\n    kind: object\n    key: a guard\n"
            f'    prototype: "@{parent}"\n',
            encoding="utf-8",
        )

    def test_parent_change_updates_inherited_values(self) -> None:
        self._snapshot_registry()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_content(root, parent="tpl")
            index = self._index(root)
            register_prototypes(index)
            assert apply_plan(
                build_plan(index, resolve_ref=self._resolver),
                index=index,
                resolve_ref=self._resolver,
            ).ok
            guard = find_entity_object("guard")
            assert guard is not None
            assert guard.attributes.get("hp") == 5

            self._write_content(root, parent="tpl2")
            index2 = self._index(root)
            assert apply_plan(
                build_plan(index2, resolve_ref=self._resolver),
                index=index2,
                resolve_ref=self._resolver,
            ).ok
        assert guard.attributes.get("hp") == 9


class TestCreateOrder(BaseEvenniaTestCase):
    def _index(self, root: Path) -> ContentIndex:
        return compile_documents(LocalDirectorySource(root).documents())

    def test_deep_chain_creates_without_retrying(self) -> None:
        calls: list[str] = []

        def resolve(ref: str) -> Any:
            calls.append(ref)
            obj = find_entity_object(ref_target(ref))
            if obj is None:
                raise LookupError(f"reference '{ref}' has not been applied yet")
            return obj

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lines = ["schema_version: 1", "entities:"]
            for item in range(20):
                # Declared deepest first, the order that defeats retries:
                # item19 needs item18, which is declared later.
                target = 19 - item
                lines.append(f"  - id: item{target}")
                lines.append("    kind: object")
                lines.append(f"    key: item {target}")
                if target:
                    lines.append(f'    location: "@item{target - 1}"')
            (root / "c.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
            index = self._index(root)
            plan = build_plan(index, resolve_ref=resolve)
            calls.clear()
            report = apply_plan(plan, index=index, resolve_ref=resolve)
        assert report.ok
        # One resolution per reference, not a retry pass per dependency level.
        assert len(calls) <= 60
