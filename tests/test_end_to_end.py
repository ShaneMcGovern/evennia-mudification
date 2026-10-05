"""End-to-end: validate, plan, apply, edit, re-apply, idempotency."""

import shutil
import tempfile
from pathlib import Path
from typing import Any

from evennia.utils.test_resources import BaseEvenniaTestCase

from evennia_mudification.apply import apply_plan
from evennia_mudification.compile import ContentIndex, compile_documents
from evennia_mudification.identity import find_entity_object
from evennia_mudification.models import ref_target
from evennia_mudification.plan import build_plan
from evennia_mudification.source import LocalDirectorySource
from evennia_mudification.validate import validate_index

CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "basic"


class TestEndToEnd(BaseEvenniaTestCase):
    def _load(self, root: Path) -> ContentIndex:
        index = compile_documents(LocalDirectorySource(root).documents())
        assert validate_index(index) == []
        return index

    def _resolve(self, ref: str) -> Any:
        obj = find_entity_object(ref_target(ref))
        assert obj is not None, ref
        return obj

    def test_full_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "content"
            shutil.copytree(CORPUS, root)
            index = self._load(root)

            plan = build_plan(index, resolve_ref=self._resolve)
            assert {
                change.entity_id for change in plan.changes if change.action == "create"
            } == {
                "square",
                "inn",
                "square-inn",
                "signpost",
            }
            assert apply_plan(plan, index=index, resolve_ref=self._resolve).ok

            square = find_entity_object("square")
            inn = find_entity_object("inn")
            door = find_entity_object("square-inn")
            signpost = find_entity_object("signpost")
            assert square is not None
            assert inn is not None
            assert door is not None
            assert signpost is not None
            assert door.location == square
            assert door.destination == inn
            assert signpost.location == square
            assert square.tags.get(category="mudification", return_list=True) == [
                "square"
            ]

            assert build_plan(self._load(root), resolve_ref=self._resolve).is_empty()

            square.db.notes = "builder scribbles"

            corpus_file = root / "village.yaml"
            text = corpus_file.read_text(encoding="utf-8")
            text = text.replace("A well-worn square.", "A busy market square.")
            text = text.replace("The Wayfarer's Inn", "The Weary Wayfarer")
            corpus_file.write_text(text, encoding="utf-8")

            index2 = self._load(root)
            plan2 = build_plan(index2, resolve_ref=self._resolve)
            assert {change.entity_id for change in plan2.changes} == {"square", "inn"}
            assert apply_plan(plan2, index=index2, resolve_ref=self._resolve).ok

            square.refresh_from_db()
            inn.refresh_from_db()
            assert square.db.desc == "A busy market square.\n"
            assert inn.key == "The Weary Wayfarer"
            assert square.db.notes == "builder scribbles"  # undeclared state survived
