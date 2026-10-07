"""Compile declared entities into Evennia prototype dictionaries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.conf import settings

from evennia_mudification.compile import ContentIndex
from evennia_mudification.identity import ENTITY_TAG_CATEGORY, SOURCE_TAG_CATEGORY
from evennia_mudification.models import (
    Entity,
    ExitEntity,
    ObjectEntity,
    PrototypeEntity,
    ref_target,
)

RefResolver = Callable[[str], Any]

_DEFAULT_TYPECLASS_SETTING = {
    "room": "BASE_ROOM_TYPECLASS",
    "exit": "BASE_EXIT_TYPECLASS",
    "object": "BASE_OBJECT_TYPECLASS",
    "prototype": "BASE_OBJECT_TYPECLASS",
}

_ENGINE_TAG_CATEGORIES = frozenset({ENTITY_TAG_CATEGORY, SOURCE_TAG_CATEGORY})

_REGISTERED_KEYS: set[str] = set()


def registered_keys() -> frozenset[str]:
    """Template keys this engine has registered as module prototypes."""
    return frozenset(_REGISTERED_KEYS)


def game_prototype_keys() -> set[str]:
    """Prototype keys the game already ships as module prototypes."""
    from evennia.prototypes.prototypes import search_prototype

    return {
        prototype.get("prototype_key", "") for prototype in search_prototype(no_db=True)
    }


def entity_to_prototype(
    entity: Entity,
    *,
    index: ContentIndex,
    resolve_ref: RefResolver,
) -> dict[str, Any]:
    """Build the prototype dict Evennia's spawner will consume."""
    typeclass = entity.typeclass
    if typeclass is None and not (
        isinstance(entity, ObjectEntity) and entity.prototype
    ):
        typeclass = getattr(settings, _DEFAULT_TYPECLASS_SETTING[entity.kind])
    attrs = [(name, value) for name, value in entity.attrs.items()]
    if entity.desc is not None and "desc" not in entity.attrs:
        attrs.append(("desc", entity.desc))
    prototype: dict[str, Any] = {
        "prototype_key": entity.id,
        "key": entity.key,
        "tags": [
            *entity.tags.items(),
            (entity.id, ENTITY_TAG_CATEGORY),
            (index.entity_sources[entity.id], SOURCE_TAG_CATEGORY),
        ],
    }
    if typeclass is not None:
        prototype["typeclass"] = typeclass
    # Omit empty declarations: Evennia reads a missing key as "leave the live
    # value alone", and declaring "" / [] would report and clear state the
    # content never mentioned.
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
        if entity.prototype:
            prototype["prototype_parent"] = ref_target(entity.prototype)
        if entity.location:
            prototype["location"] = resolve_ref(entity.location)
        if entity.home:
            prototype["home"] = resolve_ref(entity.home)
    return prototype


def effective_prototype(prototype: dict[str, Any]) -> dict[str, Any]:
    """Resolve the template chain the way Evennia's spawner does.

    Evennia cannot report which prototype a live object was spawned from, so
    the inherited fields themselves are what a plan can compare and update.
    """
    if not prototype.get("prototype_parent"):
        return prototype
    from evennia.prototypes.spawner import flatten_prototype

    flattened: dict[str, Any] = flatten_prototype(prototype, no_db=True)
    return flattened


def register_prototypes(index: ContentIndex) -> int:
    """Register prototype-kind entities as read-only module prototypes.

    A key the game already ships is never overwritten; validation reports it as
    `prototype-key-taken` before this runs. Templates this engine registered
    before and the content no longer declares are deregistered.
    """

    def _no_refs(ref: str) -> Any:  # pragma: no cover - templates declare no refs
        raise LookupError(f"prototype entities have no object references ({ref})")

    from evennia.prototypes.prototypes import (
        _MODULE_PROTOTYPES,  # no public deregistration API
        homogenize_prototype,
        load_module_prototypes,
    )

    declared: dict[str, dict[str, Any]] = {}
    for entity in index.entities.values():
        if not isinstance(entity, PrototypeEntity):
            continue
        prototype = entity_to_prototype(entity, index=index, resolve_ref=_no_refs)
        # Engine and source tags would be inherited onto every spawned child,
        # corrupting managed-id identity. Declared template tags stay:
        # inheriting those is what a template is for.
        prototype["tags"] = [
            entry
            for entry in prototype["tags"]
            if entry[1] not in _ENGINE_TAG_CATEGORIES
        ]
        declared[entity.id] = prototype

    # Before deregistering, so our own previous registration is not mistaken
    # for a game prototype and refused.
    game_keys = game_prototype_keys() - _REGISTERED_KEYS
    for key in _REGISTERED_KEYS - declared.keys():
        _MODULE_PROTOTYPES.pop(key, None)
    _REGISTERED_KEYS.clear()

    registerable = {
        key: prototype for key, prototype in declared.items() if key not in game_keys
    }
    if registerable:
        # `load_module_prototypes` stores dicts as-is, so normalize to the
        # canonical four-tuple attrs that spawn's inheritance expects.
        # `override=True` keeps re-registration idempotent.
        load_module_prototypes(
            *(homogenize_prototype(prototype) for prototype in registerable.values()),
            override=True,
        )
    _REGISTERED_KEYS.update(registerable)
    return len(registerable)
