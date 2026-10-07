"""Tag-based identity for objects the engine manages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

ENTITY_TAG_CATEGORY = "mudification"
SOURCE_TAG_CATEGORY = "mudification_source"


def _carries_source_tag(obj: DefaultObject) -> bool:
    # Both tags together mark an object as engine-managed; a lone entity tag,
    # hand-added or inherited from a copy, is never enough on its own.
    return bool(obj.tags.get(category=SOURCE_TAG_CATEGORY, return_list=True))


@dataclass(frozen=True)
class ManagedWorld:
    """Every engine-managed object, keyed by entity id.

    Duplicates stay visible: several live copies of one id are all listed, and
    the first is what a single lookup returns.
    """

    objects: dict[str, list[Any]]

    @property
    def by_id(self) -> dict[str, Any]:
        return {key: copies[0] for key, copies in self.objects.items()}

    @property
    def ids(self) -> set[str]:
        return set(self.objects)

    def get(self, entity_id: str) -> Any | None:
        copies = self.objects.get(entity_id)
        return copies[0] if copies else None

    def all(self, entity_id: str) -> list[Any]:
        return list(self.objects.get(entity_id, []))


def load_managed_world() -> ManagedWorld:
    """Load every managed object in a fixed number of queries.

    One query joins the entity and source tag rows to object ids and one
    fetches the objects, with the tags and attributes the diff reads
    prefetched; the per-entity lookups these replace cost a query each and
    dominate planning on a real world. An object counts only when it carries
    both tags, like `find_entity_objects`, and the first object carrying an id
    wins when several do.
    """
    from evennia.objects.models import ObjectDB
    from evennia.typeclasses.models import Tag

    rows = Tag.objects.filter(
        db_category__in=(ENTITY_TAG_CATEGORY, SOURCE_TAG_CATEGORY)
    ).values_list("db_category", "db_key", "objectdb__id")
    entity_objects: dict[str, list[int]] = {}
    sourced: set[int] = set()
    for category, key, object_id in rows:
        if object_id is None:
            continue
        if category == ENTITY_TAG_CATEGORY:
            entity_objects.setdefault(str(key), []).append(object_id)
        else:
            sourced.add(object_id)
    wanted = {
        key: [object_id for object_id in object_ids if object_id in sourced]
        for key, object_ids in entity_objects.items()
    }
    loaded = {
        obj.pk: obj
        for obj in ObjectDB.objects.filter(
            pk__in={object_id for ids in wanted.values() for object_id in ids}
        ).prefetch_related("db_tags", "db_attributes")
    }
    managed: dict[str, list[Any]] = {}
    for key, object_ids in wanted.items():
        copies = [loaded[object_id] for object_id in object_ids if object_id in loaded]
        if copies:
            managed[key] = copies
    return ManagedWorld(objects=managed)


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
    return load_managed_world().ids
