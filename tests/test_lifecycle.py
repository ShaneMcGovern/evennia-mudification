"""End-to-end: counts, nesting, reverse exits, templates and prune."""

import shutil
import tempfile
from pathlib import Path
from typing import Any

from evennia.utils import create
from evennia.utils.test_resources import BaseEvenniaTestCase

from evennia_mudification.apply import apply_plan
from evennia_mudification.compile import ContentIndex, compile_documents
from evennia_mudification.identity import find_entity_object, managed_ids
from evennia_mudification.models import ref_target
from evennia_mudification.plan import build_plan
from evennia_mudification.proto import register_prototypes
from evennia_mudification.prune import execute_prune, plan_prune
from evennia_mudification.source import LocalDirectorySource
from evennia_mudification.validate import validate_index

CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "lifecycle"


class TestLifecycle(BaseEvenniaTestCase):
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
            register_prototypes(index)
            plan = build_plan(index, resolve_ref=self._resolve)
            assert {
                change.entity_id for change in plan.changes if change.action == "create"
            } == {
                "hall",
                "chest",
                "coin",
                "cellar",
                "hall-cellar",
                "hall-cellar:reverse",
                "rats#1",
                "rats#2",
                "rats#3",
                "goblin_guard",
            }
            assert apply_plan(plan, index=index, resolve_ref=self._resolve).ok
            assert build_plan(self._load(root), resolve_ref=self._resolve).is_empty()

            hall: Any = find_entity_object("hall")
            chest: Any = find_entity_object("chest")
            coin: Any = find_entity_object("coin")
            reverse: Any = find_entity_object("hall-cellar:reverse")
            guard: Any = find_entity_object("goblin_guard")
            assert chest.location == hall
            assert coin.location == chest
            assert reverse.location == find_entity_object("cellar")
            assert reverse.key == "The Great Hall"
            assert guard.db.hp == 5
            assert find_entity_object("rats#3") is not None

            world = root / "world.yaml"
            world.write_text(
                world.read_text(encoding="utf-8").replace("count: 3", "count: 2"),
                encoding="utf-8",
            )
            index2 = self._load(root)
            plan2 = build_plan(index2, resolve_ref=self._resolve)
            assert plan2.changes == []
            assert plan2.retirements == {"rats#3"}
            prune_plan = plan_prune(plan2.retirements, fallback=hall)
            report = execute_prune(prune_plan)
            assert report.ok
            assert report.destroyed == 1
            assert find_entity_object("rats#3") is None
            assert "rats#1" in managed_ids()

            # An untagged occupant evacuates to its home, the first-created
            # hall (the test DEFAULT_HOME).
            cellar: Any = find_entity_object("cellar")
            crate = create.create_object(
                "evennia.objects.objects.DefaultObject",
                key="a stray crate",
                location=cellar,
            )
            world.write_text(
                world.read_text(encoding="utf-8")
                .replace("  - id: cellar\n    kind: room\n    key: the cellar\n", "")
                .replace(
                    "  - id: hall-cellar\n    kind: exit\n    key: cellar stairs\n"
                    '    location: "@hall"\n    destination: "@cellar"\n'
                    "    reverse: true\n",
                    "",
                ),
                encoding="utf-8",
            )
            index3 = self._load(root)
            plan3 = build_plan(index3, resolve_ref=self._resolve)
            assert plan3.changes == []
            assert plan3.retirements == {
                "cellar",
                "hall-cellar",
                "hall-cellar:reverse",
            }
            prune_plan3 = plan_prune(plan3.retirements, fallback=hall)
            assert prune_plan3.errors == []
            reasons = {
                evacuation.occupant.key: evacuation.reason
                for evacuation in prune_plan3.evacuations
            }
            assert reasons == {"a stray crate": "home"}
            assert prune_plan3.evacuations[0].destination == hall
            report3 = execute_prune(prune_plan3)
            assert report3.ok
            assert report3.evacuated == 1
            crate.refresh_from_db()
            assert crate.home == hall
            assert crate.location == hall
            assert find_entity_object("cellar") is None
