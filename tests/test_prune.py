"""Tests for prune planning and execution."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from django.test import override_settings
from evennia.objects.models import ObjectDB
from evennia.objects.objects import DefaultCharacter
from evennia.utils import create
from evennia.utils.test_resources import BaseEvenniaTestCase

from evennia_mudification import prune
from evennia_mudification.apply import apply_plan
from evennia_mudification.compile import compile_documents
from evennia_mudification.identity import (
    ENTITY_TAG_CATEGORY,
    SOURCE_TAG_CATEGORY,
    ManagedWorld,
    find_entity_object,
)
from evennia_mudification.models import ref_target
from evennia_mudification.plan import build_plan
from evennia_mudification.prune import execute_prune, plan_prune, resolve_fallback
from evennia_mudification.source import LocalDirectorySource

CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "basic"


class TestPrune(BaseEvenniaTestCase):
    def _spawn_world(self) -> None:
        index = compile_documents(LocalDirectorySource(CORPUS).documents())

        def resolve(ref: str) -> Any:
            obj = find_entity_object(ref_target(ref))
            assert obj is not None, ref
            return obj

        assert apply_plan(
            build_plan(index, resolve_ref=resolve), index=index, resolve_ref=resolve
        ).ok

    def test_retiring_room_evacuates_occupants(self) -> None:
        self._spawn_world()
        hall = find_entity_object("square")
        inn = find_entity_object("inn")
        wanderer = create.create_object(
            "evennia.objects.objects.DefaultCharacter", key="Wanderer", location=hall
        )
        wanderer.home = inn
        crate = create.create_object(
            "evennia.objects.objects.DefaultObject", key="crate", location=hall
        )
        prune_plan = plan_prune({"square"}, fallback=inn)
        assert prune_plan.errors == []
        reasons = {
            evacuation.occupant.key: evacuation.reason
            for evacuation in prune_plan.evacuations
        }
        assert reasons["Wanderer"] == "home"
        assert reasons["crate"] == "fallback"
        assert "evacuate Wanderer -> The Wayfarer's Inn (home)" in prune_plan.render()
        report = execute_prune(prune_plan)
        assert report.ok
        wanderer.refresh_from_db()
        crate.refresh_from_db()
        assert wanderer.location == inn
        assert crate.location == inn
        assert find_entity_object("square") is None

    def test_home_that_is_retired_uses_fallback(self) -> None:
        self._spawn_world()
        hall = find_entity_object("square")
        inn = find_entity_object("inn")
        stranded = create.create_object(
            "evennia.objects.objects.DefaultCharacter", key="Stranded", location=hall
        )
        stranded.home = hall
        prune_plan = plan_prune({"square"}, fallback=inn)
        reasons = {
            evacuation.occupant.key: evacuation.reason
            for evacuation in prune_plan.evacuations
        }
        assert reasons["Stranded"] == "fallback"

    def test_retired_occupants_are_not_evacuated(self) -> None:
        # Everything inside retires together, so no fallback is needed.
        self._spawn_world()
        prune_plan = plan_prune({"square", "square-inn", "signpost"}, fallback=None)
        assert prune_plan.errors == []
        assert prune_plan.evacuations == []

    def test_unresolvable_fallback_refuses(self) -> None:
        self._spawn_world()
        with override_settings(MUDIFICATION_FALLBACK_ROOM="#99999", DEFAULT_HOME=None):
            assert resolve_fallback() is None
        with override_settings(MUDIFICATION_FALLBACK_ROOM="nowhere", DEFAULT_HOME=None):
            assert resolve_fallback() is None
        with override_settings(MUDIFICATION_FALLBACK_ROOM=None, DEFAULT_HOME=None):
            assert resolve_fallback() is None
        prune_plan = plan_prune({"square"}, fallback=None)
        assert [finding.code for finding in prune_plan.errors] == ["fallback-missing"]
        assert "fallback-missing" in prune_plan.render()
        assert prune_plan.evacuations == []

    def test_fallback_finding_is_anchored_at_the_content_root(self) -> None:
        self._spawn_world()
        with override_settings(
            MUDIFICATION_FALLBACK_ROOM=None,
            DEFAULT_HOME=None,
            MUDIFICATION_CONTENT_PATH="/content/root",
        ):
            prune_plan = plan_prune({"square"}, fallback=None)
        assert [finding.source for finding in prune_plan.errors] == ["/content/root"]

    def test_fallback_that_is_retired_refuses(self) -> None:
        self._spawn_world()
        hall = find_entity_object("square")
        inn = find_entity_object("inn")
        create.create_object(
            "evennia.objects.objects.DefaultObject", key="crate", location=hall
        )
        prune_plan = plan_prune({"square", "inn"}, fallback=inn)
        assert [finding.code for finding in prune_plan.errors] == ["fallback-missing"]
        assert "fallback-missing" in prune_plan.render()
        assert prune_plan.evacuations == []

    def test_non_room_fallback_refuses(self) -> None:
        self._spawn_world()
        hall = find_entity_object("square")
        signpost = find_entity_object("signpost")
        create.create_object(
            "evennia.objects.objects.DefaultObject", key="crate", location=hall
        )
        prune_plan = plan_prune({"square"}, fallback=signpost)
        assert [finding.code for finding in prune_plan.errors] == ["fallback-missing"]
        assert "fallback-missing" in prune_plan.render()
        assert prune_plan.evacuations == []

    def test_object_contents_go_to_fallback(self) -> None:
        self._spawn_world()
        inn = find_entity_object("inn")
        chest = create.create_object(
            "evennia.objects.objects.DefaultObject",
            key="chest",
            tags=[
                ("chest", ENTITY_TAG_CATEGORY),
                ("village.yaml", SOURCE_TAG_CATEGORY),
            ],
        )
        coin = create.create_object(
            "evennia.objects.objects.DefaultObject", key="coin", location=chest
        )
        prune_plan = plan_prune({"chest"}, fallback=inn)
        report = execute_prune(prune_plan)
        assert report.ok
        coin.refresh_from_db()
        assert coin.location == inn
        assert find_entity_object("chest") is None

    def test_duplicate_objects_retire_in_one_run(self) -> None:
        for _ in range(2):
            create.create_object(
                "evennia.objects.objects.DefaultObject",
                key="ghost copy",
                tags=[
                    ("ghost", ENTITY_TAG_CATEGORY),
                    ("village.yaml", SOURCE_TAG_CATEGORY),
                ],
            )
        prune_plan = plan_prune({"ghost"}, fallback=None)
        assert prune_plan.errors == []
        report = execute_prune(prune_plan)
        assert report.ok
        assert report.destroyed == 2
        assert find_entity_object("ghost") is None

    def test_exits_are_not_evacuated_and_die_with_the_room(self) -> None:
        self._spawn_world()
        hall = find_entity_object("square")
        inn = find_entity_object("inn")
        door = create.create_object(
            "evennia.objects.objects.DefaultExit",
            key="side door",
            location=hall,
            destination=inn,
        )
        prune_plan = plan_prune({"square"}, fallback=inn)
        assert prune_plan.errors == []
        assert "side door" not in {
            evacuation.occupant.key for evacuation in prune_plan.evacuations
        }
        report = execute_prune(prune_plan)
        assert report.ok
        assert not ObjectDB.objects.filter(pk=door.pk).exists()

    def test_vetoed_move_fails_the_evacuation(self) -> None:
        self._spawn_world()
        hall = find_entity_object("square")
        inn = find_entity_object("inn")
        rooted = create.create_object(_RootedCharacter, key="Rooted", location=hall)
        rooted.home = inn
        prune_plan = plan_prune({"square"}, fallback=inn)
        report = execute_prune(prune_plan)
        assert not report.ok
        assert "evacuate Rooted: FAILED" in report.render()
        # A failed evacuation skips the destruction phase entirely.
        assert report.destroyed == 0
        assert find_entity_object("square") is not None

    def test_delete_returning_none_is_a_failure(self) -> None:
        room = SimpleNamespace(key="room", contents=[], delete=lambda: None)
        with mock.patch.object(prune, "find_entity_objects", return_value=[room]):
            prune_plan = plan_prune({"square"}, fallback=None)
            report = execute_prune(prune_plan)
        assert not report.ok
        assert report.destroyed == 0
        assert "destroy square: FAILED" in report.render()

    def test_evacuation_failure_is_reported(self) -> None:
        delete = mock.Mock()
        room = SimpleNamespace(key="room", contents=[_BadOccupant()], delete=delete)
        fallback = create.create_object(
            "evennia.objects.objects.DefaultRoom", key="fallback"
        )
        world = ManagedWorld(objects={"square": [room]})
        prune_plan = plan_prune({"square"}, fallback=fallback, world=world)
        assert [evacuation.reason for evacuation in prune_plan.evacuations] == [
            "fallback"
        ]
        with mock.patch.object(prune, "find_entity_objects", return_value=[room]):
            report = execute_prune(prune_plan)
        assert not report.ok
        assert "evacuate bad: FAILED: boom" in report.render()
        # A failed evacuation skips the destruction phase entirely.
        assert report.destroyed == 0
        assert not [result for result in report.results if result.action == "destroy"]
        delete.assert_not_called()

    def test_vetoed_deletion_is_reported(self) -> None:
        room = SimpleNamespace(key="room", contents=[], delete=lambda: False)
        with mock.patch.object(prune, "find_entity_objects", return_value=[room]):
            prune_plan = plan_prune({"square"}, fallback=None)
            report = execute_prune(prune_plan)
        assert not report.ok
        assert report.destroyed == 0
        assert "destroy square: FAILED: deletion was vetoed" in report.render()

    def test_destruction_failure_and_missing_object(self) -> None:
        def _boom() -> None:
            raise RuntimeError("boom")

        room = SimpleNamespace(key="room", contents=[], delete=_boom)
        with mock.patch.object(
            prune,
            "find_entity_objects",
            side_effect=lambda entity_id: [] if entity_id == "stale" else [room],
        ):
            prune_plan = plan_prune({"stale", "square"}, fallback=None)
            assert prune_plan.errors == []
            report = execute_prune(prune_plan)
        assert not report.ok
        assert "destroy square: FAILED: boom" in report.render()
        assert "stale" not in report.render()  # already gone; nothing to report
        assert report.destroyed == 0


class _RootedCharacter(DefaultCharacter):
    """A character whose move hooks veto every move."""

    def at_pre_move(
        self, destination: Any, move_type: str | None = None, **kwargs: Any
    ) -> bool:
        return False


class _FakeTags:
    def get(self, **kwargs: object) -> list[str]:
        return []


class _BadOccupant:
    """An occupant whose move always fails."""

    key = "bad"
    home = None
    tags = _FakeTags()

    def move_to(self, destination: Any, move_type: str | None = None) -> bool:
        raise RuntimeError("boom")
