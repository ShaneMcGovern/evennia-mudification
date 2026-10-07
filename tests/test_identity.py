"""Tests for tag-based entity identity."""

from typing import Any

from evennia.utils import create
from evennia.utils.test_resources import BaseEvenniaTestCase

from evennia_mudification.identity import (
    ENTITY_TAG_CATEGORY,
    SOURCE_TAG_CATEGORY,
    find_entity_object,
    find_entity_objects,
    managed_ids,
)


class TestIdentity(BaseEvenniaTestCase):
    def _make(self, entity_id: str) -> Any:
        return create.create_object(
            "evennia.objects.objects.DefaultObject",
            key=f"obj-{entity_id}",
            tags=[
                (entity_id, ENTITY_TAG_CATEGORY),
                ("village.yaml", SOURCE_TAG_CATEGORY),
            ],
        )

    def test_find_entity_object(self) -> None:
        obj = self._make("square")
        assert find_entity_object("square") == obj
        assert find_entity_object("missing") is None

    def test_managed_ids(self) -> None:
        self._make("square")
        self._make("inn")
        assert managed_ids() == {"square", "inn"}

    def test_entity_tag_alone_is_not_managed(self) -> None:
        create.create_object(
            "evennia.objects.objects.DefaultObject",
            key="impostor",
            tags=[("ghost", ENTITY_TAG_CATEGORY)],
        )
        assert find_entity_object("ghost") is None
        assert "ghost" not in managed_ids()

    def test_duplicate_managed_objects_are_all_returned(self) -> None:
        first = self._make("square")
        second = self._make("square")
        matches = find_entity_objects("square")
        assert {obj.pk for obj in matches} == {first.pk, second.pk}
        assert find_entity_object("square") is not None
