"""Compare desired content with the live database and describe the diff."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from evennia.prototypes.spawner import flatten_diff, prototype_diff_from_object

from evennia_mudification.compile import ContentIndex
from evennia_mudification.identity import find_entity_objects, managed_ids
from evennia_mudification.models import PrototypeEntity
from evennia_mudification.proto import RefResolver, entity_to_prototype

Action = Literal["create", "update"]

_META_KEYS = {
    "prototype_key",
    "prototype_desc",
    "prototype_tags",
    "prototype_locks",
    "prototype_parent",
}

_REF_KEYS = ("location", "home", "destination")

_UNRESOLVED = object()

# Fields Evennia's diff gets wrong: stored forms are canonicalized differently
# from the declared ones, so `declared_diff` compares these itself.
_SELF_COMPARED_KEYS = {"locks", "permissions", "aliases", "tags"}


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
    duplicates: dict[str, int] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.changes and not self.retirements

    def render(self) -> str:
        lines = [change.render() for change in self.changes]
        lines += [
            f"retire {entity_id} (reported only)"
            for entity_id in sorted(self.retirements)
        ]
        lines += [
            f"duplicate {entity_id}: {count} live objects"
            for entity_id, count in sorted(self.duplicates.items())
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


# Evennia canonicalizes these fields on storage (whitespace for locks,
# stripping and lowercasing for the rest), so the declared side is normalized
# the same way and compared as a subset: extra live values are kept, and a
# whole-value comparison would report a phantom update forever.
def _declared_locks_are_live(lockstring: str, obj: Any) -> bool:
    """True when every declared lock entry is already on the object."""
    live = {_normalize_lock(entry) for entry in obj.locks.all()}
    declared = [
        _normalize_lock(entry) for entry in lockstring.split(";") if entry.strip()
    ]
    return all(entry in live for entry in declared)


def _declared_permissions_are_live(permissions: list[str], obj: Any) -> bool:
    """True when every declared permission is already on the object."""
    live = {str(permission).lower() for permission in obj.permissions.all()}
    return all(str(permission).strip().lower() in live for permission in permissions)


def _declared_aliases_are_live(aliases: list[str], obj: Any) -> bool:
    """Declared aliases are unchanged when each exists live."""
    live = {alias.strip().lower() for alias in obj.aliases.all()}
    return all(alias.strip().lower() in live for alias in aliases)


def _declared_tags_are_live(tags: list[Any], obj: Any) -> bool:
    """Declared tags are unchanged when each (key, category) exists live."""
    live = {
        (key.strip().lower(), (category or "").strip().lower())
        for key, category in obj.tags.all(return_key_and_category=True)
    }
    for entry in tags:
        key = entry[0]
        category = entry[1] if len(entry) > 1 else None
        if (str(key).strip().lower(), (category or "").strip().lower()) not in live:
            return False
    return True


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
    if prototype.get("aliases") and not _declared_aliases_are_live(
        prototype["aliases"], obj
    ):
        declared["aliases"] = "UPDATE"
    if prototype.get("tags") and not _declared_tags_are_live(prototype["tags"], obj):
        declared["tags"] = "UPDATE"
    return declared


def build_plan(index: ContentIndex, *, resolve_ref: RefResolver) -> Plan:
    """Diff every entity against the database; prototype templates are skipped."""
    plan = Plan()
    for entity in index.entities.values():
        if isinstance(entity, PrototypeEntity):
            # Templates are not world objects; they have no plan of their own.
            continue
        matches = find_entity_objects(entity.id)
        existing = matches[0] if matches else None
        if existing is None:
            plan.changes.append(PlannedChange(entity.id, "create"))
            continue
        if len(matches) > 1:
            plan.duplicates[entity.id] = len(matches)
        unresolved: list[str] = []

        # Sentinel for a ref whose target is declared in this same index but
        # has no live object yet; the create pass makes it live before this
        # entity's update phase resolves refs again.
        def _tolerant(ref: str) -> Any:
            try:
                return resolve_ref(ref)
            except LookupError:
                return _UNRESOLVED

        prototype = entity_to_prototype(entity, index=index, resolve_ref=_tolerant)
        for key in ("location", "home", "destination"):
            if prototype.get(key) is _UNRESOLVED:
                del prototype[key]
                unresolved.append(key)
        if len(matches) > 1:
            plan.duplicates[entity.id] = len(matches)
        diff = declared_diff(prototype, existing)
        for key in unresolved:
            diff[key] = "UPDATE"
        if diff:
            plan.changes.append(PlannedChange(entity.id, "update", diff))
    plan.retirements = managed_ids() - set(index.entities)
    return plan
