"""Compare desired content with the live database and describe the diff."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from evennia.prototypes.spawner import flatten_diff, prototype_diff_from_object

from evennia_mudification.compile import ContentIndex
from evennia_mudification.identity import find_entity_object, managed_ids
from evennia_mudification.models import PrototypeEntity
from evennia_mudification.proto import RefResolver, entity_to_prototype

Action = Literal["create", "update"]

_META_KEYS = {"prototype_key", "prototype_desc", "prototype_tags", "prototype_locks"}

_REF_KEYS = ("location", "home", "destination")

# Fields Evennia's object diff gets wrong for declared-subset semantics: the
# stored forms are canonicalized differently from what the content declares.
# `declared_diff` compares these two itself.
_SELF_COMPARED_KEYS = {"locks", "permissions"}


class UnsupportedEntityError(RuntimeError):
    """Raised when content uses an entity kind this milestone cannot apply."""


@dataclass
class PlannedChange:
    """One entity with a pending create or update."""

    entity_id: str
    action: Action
    diff: dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        if self.action == "create":
            return f"create {self.entity_id}"
        changed = ", ".join(sorted(self.diff))
        return f"update {self.entity_id}: {changed}"


@dataclass
class Plan:
    """The full diff between content and database."""

    changes: list[PlannedChange] = field(default_factory=list)
    retirements: set[str] = field(default_factory=set)

    def is_empty(self) -> bool:
        return not self.changes and not self.retirements

    def render(self) -> str:
        lines = [change.render() for change in self.changes]
        lines += [
            f"retire {entity_id} (reported only)"
            for entity_id in sorted(self.retirements)
        ]
        return "\n".join(lines) if lines else "no changes"


def _comparable(prototype: dict[str, Any]) -> dict[str, Any]:
    """Replace resolved object references with dbrefs before diffing.

    ``prototype_from_object`` stores location/home/destination as dbrefs, so an
    unchanged reference would otherwise compare object-vs-string and report an
    update.
    """
    comparable = dict(prototype)
    for key in _REF_KEYS:
        dbref = getattr(comparable.get(key), "dbref", None)
        if isinstance(dbref, str):
            comparable[key] = dbref
    return comparable


def _normalize_lock(entry: str) -> str:
    """Strip cosmetic whitespace from one `name:value` lock entry."""
    name, separator, value = entry.partition(":")
    if not separator:
        return entry.strip()
    return f"{name.strip()}:{value.strip()}"


def _declared_locks_are_live(lockstring: str, obj: Any) -> bool:
    """True when every declared lock entry is already on the object.

    Evennia stores the full default lockset plus the declared locks, so
    comparing the declared string against ``obj.locks.all()`` as a whole would
    report a phantom update forever after apply. Declared-subset semantics:
    every declared entry must be present, and extra live locks are kept.
    """
    live = {_normalize_lock(entry) for entry in obj.locks.all()}
    declared = [
        _normalize_lock(entry) for entry in lockstring.split(";") if entry.strip()
    ]
    return all(entry in live for entry in declared)


def _declared_permissions_are_live(permissions: list[str], obj: Any) -> bool:
    """True when every declared permission is already on the object.

    Evennia lowercases permissions on add, so a declared ``Builders`` must be
    compared case-insensitively against ``obj.permissions.all()``. Declared
    entries are added; live ones the content no longer declares are kept.
    """
    live = {str(permission).lower() for permission in obj.permissions.all()}
    return all(str(permission).lower() in live for permission in permissions)


def declared_diff(prototype: dict[str, Any], obj: Any) -> dict[str, Any]:
    """Field-level diff limited to the keys the content declares."""
    diff, _ = prototype_diff_from_object(_comparable(prototype), obj)
    flat = flatten_diff(diff)
    declared = {
        key: instruction
        for key, instruction in flat.items()
        if key not in _META_KEYS
        and key not in _SELF_COMPARED_KEYS
        and key in prototype
        and instruction != "KEEP"
    }
    if "locks" in prototype and not _declared_locks_are_live(prototype["locks"], obj):
        declared["locks"] = "UPDATE"
    if "permissions" in prototype and not _declared_permissions_are_live(
        prototype["permissions"], obj
    ):
        declared["permissions"] = "UPDATE"
    return declared


def build_plan(index: ContentIndex, *, resolve_ref: RefResolver) -> Plan:
    """Diff every entity against the database; refuses unsupported kinds."""
    plan = Plan()
    for entity in index.entities.values():
        if isinstance(entity, PrototypeEntity):
            raise UnsupportedEntityError(
                f"entity '{entity.id}': prototype entities are not supported yet"
            )
        existing = find_entity_object(entity.id)
        if existing is None:
            plan.changes.append(PlannedChange(entity.id, "create"))
            continue
        prototype = entity_to_prototype(entity, index=index, resolve_ref=resolve_ref)
        diff = declared_diff(prototype, existing)
        if diff:
            plan.changes.append(PlannedChange(entity.id, "update", diff))
    plan.retirements = managed_ids() - set(index.entities)
    return plan
