"""Tests for tag-based entity identity."""

from typing import Any

from evennia.utils import create
from evennia.utils.test_resources import BaseEvenniaTestCase

from evennia_mudification.identity import (
    ENTITY_TAG_CATEGORY,
    SOURCE_TAG_CATEGORY,
    find_entity_object,
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
