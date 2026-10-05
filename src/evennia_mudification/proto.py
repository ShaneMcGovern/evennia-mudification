"""Compile declared entities into Evennia prototype dictionaries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.conf import settings

from evennia_mudification.compile import ContentIndex
from evennia_mudification.identity import ENTITY_TAG_CATEGORY, SOURCE_TAG_CATEGORY
from evennia_mudification.models import Entity, ExitEntity, ObjectEntity

RefResolver = Callable[[str], Any]

_DEFAULT_TYPECLASS_SETTING = {
    "room": "BASE_ROOM_TYPECLASS",
    "exit": "BASE_EXIT_TYPECLASS",
    "object": "BASE_OBJECT_TYPECLASS",
    "prototype": "BASE_OBJECT_TYPECLASS",
}


def entity_to_prototype(
    entity: Entity,
    *,
    index: ContentIndex,
    resolve_ref: RefResolver,
) -> dict[str, Any]:
    """Build the prototype dict Evennia's spawner will consume."""
    typeclass = entity.typeclass or getattr(
        settings, _DEFAULT_TYPECLASS_SETTING[entity.kind]
    )
    attrs = [(name, value) for name, value in entity.attrs.items()]
    if entity.desc is not None and "desc" not in entity.attrs:
        attrs.append(("desc", entity.desc))
    prototype: dict[str, Any] = {
        "prototype_key": entity.id,
        "typeclass": typeclass,
        "key": entity.key,
        "tags": [
            *entity.tags.items(),
            (entity.id, ENTITY_TAG_CATEGORY),
            (index.entity_sources[entity.id], SOURCE_TAG_CATEGORY),
        ],
    }
    # Empty declarations are omitted, not declared as empty: Evennia's diff
    # treats a missing key as "leave the live value alone", which is the
    # ownership model these prototypes promise. Declaring "" / [] explicitly
    # would report (and on update clear) state the content never mentioned -
    # including builder-added attrs/aliases on an entity that declares none.
    if entity.aliases:
        prototype["aliases"] = list(entity.aliases)
    if attrs:
        prototype["attrs"] = attrs
    locks = ";".join(f"{name}:{value}" for name, value in entity.locks.items())
    if locks:
        prototype["locks"] = locks
    if entity.permissions:
        prototype["permissions"] = list(entity.permissions)
    if isinstance(entity, ExitEntity):
        prototype["location"] = resolve_ref(entity.location)
        prototype["destination"] = resolve_ref(entity.destination)
    elif isinstance(entity, ObjectEntity):
        if entity.location:
            prototype["location"] = resolve_ref(entity.location)
        if entity.home:
            prototype["home"] = resolve_ref(entity.home)
    return prototype
