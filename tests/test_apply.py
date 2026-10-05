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
from evennia_mudification.apply import apply_plan
from evennia_mudification.compile import ContentIndex, compile_documents
from evennia_mudification.identity import find_entity_object
from evennia_mudification.models import EntityBase, ref_target
from evennia_mudification.plan import build_plan
from evennia_mudification.proto import RefResolver, entity_to_prototype
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
