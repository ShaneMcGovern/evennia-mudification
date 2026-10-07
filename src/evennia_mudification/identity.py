"""Tag-based identity for objects the engine manages."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

ENTITY_TAG_CATEGORY = "mudification"
SOURCE_TAG_CATEGORY = "mudification_source"


def _carries_source_tag(obj: DefaultObject) -> bool:
    # Both tags together mark an object as engine-managed; a lone entity tag,
    # hand-added or inherited from a copy, is never enough on its own.
    return bool(obj.tags.get(category=SOURCE_TAG_CATEGORY, return_list=True))


def find_entity_objects(entity_id: str) -> list[DefaultObject]:
    """Return every live object carrying this managed id."""
    from evennia.objects.models import ObjectDB

    return [
        obj
        for obj in ObjectDB.objects.get_by_tag(
            key=entity_id, category=ENTITY_TAG_CATEGORY
        )
        if _carries_source_tag(obj)
    ]


def find_entity_object(entity_id: str) -> DefaultObject | None:
    """Return the first managed object for this id, or None."""
    matches = find_entity_objects(entity_id)
    return matches[0] if matches else None


def managed_ids() -> set[str]:
    """Return every entity id the engine has applied to the database."""
    from evennia.objects.models import ObjectDB

    ids: set[str] = set()
    for obj in ObjectDB.objects.get_by_tag(category=ENTITY_TAG_CATEGORY):
        if not _carries_source_tag(obj):
            continue
        ids.update(obj.tags.get(category=ENTITY_TAG_CATEGORY, return_list=True))
    return ids
