"""Tag-based identity for objects the engine manages."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

ENTITY_TAG_CATEGORY = "mudification"
SOURCE_TAG_CATEGORY = "mudification_source"


def find_entity_object(entity_id: str) -> DefaultObject | None:
    """Return the object tagged with this entity id, or None."""
    from evennia.objects.models import ObjectDB

    matches = list(
        ObjectDB.objects.get_by_tag(key=entity_id, category=ENTITY_TAG_CATEGORY)
    )
    return matches[0] if matches else None


def managed_ids() -> set[str]:
    """Return every entity id the engine has applied to the database."""
    from evennia.objects.models import ObjectDB

    ids: set[str] = set()
    for obj in ObjectDB.objects.get_by_tag(category=ENTITY_TAG_CATEGORY):
        ids.update(obj.tags.get(category=ENTITY_TAG_CATEGORY, return_list=True))
    return ids
