"""Validation for a compiled content index."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from evennia_mudification.compile import ContentIndex
from evennia_mudification.findings import Finding, Severity
from evennia_mudification.identity import ENTITY_TAG_CATEGORY, SOURCE_TAG_CATEGORY
from evennia_mudification.models import (
    EntityBase,
    ExitEntity,
    ObjectEntity,
    PrototypeEntity,
    RoomEntity,
    ref_target,
)

# Mirrors Evennia's parser: a name starts with a letter or underscore and runs
# to the first parenthesis; a backslash-escaped `$` is not a call. Narrower
# patterns silently miss names the parser would reject at spawn.
_RE_PROTFUNC = re.compile(r"(?<![\$\\])\$([^\W\d][^(]*)\(")

RESERVED_TAG_CATEGORIES = (ENTITY_TAG_CATEGORY, SOURCE_TAG_CATEGORY)


def validate_index(
    index: ContentIndex,
    *,
    check_evennia: bool = False,
    typeclass_severity: Severity = "error",
) -> list[Finding]:
    """Check references and kind constraints; collects every problem found."""
    findings: list[Finding] = []
    findings.extend(find_reserved_tag_issues(index))
    for entity in index.entities.values():
        source = index.entity_sources[entity.id]
        for ref, field_name, allowed, code in _refs_of(entity):
            target_id = ref_target(ref)
            target = index.entities.get(target_id)
            if target is None:
                findings.append(
                    Finding(
                        "error",
                        "dangling-ref",
                        f"{field_name} ref '{ref}' does not match any declared entity",
                        source,
                        entity.id,
                    )
                )
                continue
            if not isinstance(target, allowed):
                expected = "a room" if allowed == (RoomEntity,) else "a room or object"
                findings.append(
                    Finding(
                        "error",
                        code,
                        f"{field_name} '{ref}' is not {expected}",
                        source,
                        entity.id,
                    )
                )
    findings.extend(find_location_cycle_issues(index))
    findings.extend(find_prototype_ref_issues(index))
    if check_evennia:
        findings.extend(find_protfunc_issues(index))
        findings.extend(find_lockstring_issues(index))
        findings.extend(find_typeclass_issues(index, severity=typeclass_severity))
    return findings


def find_protfunc_issues(index: ContentIndex) -> list[Finding]:
    """Flag `$func(...)` references that are not registered protfuncs."""
    from evennia.prototypes.prototypes import FUNC_PARSER

    available = set(FUNC_PARSER.callables)
    findings: list[Finding] = []
    for entity in index.entities.values():
        values = [entity.key, entity.desc or "", *entity.attrs.values()]
        for text in _iter_strings(values):
            for name in _RE_PROTFUNC.findall(text):
                if name not in available:
                    findings.append(
                        Finding(
                            "error",
                            "unknown-protfunc",
                            f"${name}(...) is not a registered protfunc",
                            index.entity_sources[entity.id],
                            entity.id,
                        )
                    )
    return findings


def find_lockstring_issues(index: ContentIndex) -> list[Finding]:
    """Flag lockstrings that Evennia's validator rejects."""
    from evennia.locks.lockhandler import validate_lockstring

    findings: list[Finding] = []
    for entity in index.entities.values():
        if not entity.locks:
            continue
        lockstring = ";".join(f"{name}:{value}" for name, value in entity.locks.items())
        is_valid, error = validate_lockstring(lockstring)
        if not is_valid:
            findings.append(
                Finding(
                    "error",
                    "invalid-lock",
                    f"locks: {error}",
                    index.entity_sources[entity.id],
                    entity.id,
                )
            )
    return findings


def find_typeclass_issues(
    index: ContentIndex, *, severity: Severity = "error"
) -> list[Finding]:
    """Flag typeclass paths that cannot be imported in this environment."""
    from django.conf import settings
    from evennia.utils.utils import class_from_module

    findings: list[Finding] = []
    for entity in index.entities.values():
        if not entity.typeclass:
            continue
        try:
            class_from_module(entity.typeclass, defaultpaths=settings.TYPECLASS_PATHS)
        except ImportError as err:
            findings.append(
                Finding(
                    severity,
                    "typeclass-unresolved",
                    f"typeclass '{entity.typeclass}' did not resolve: {err}",
                    index.entity_sources[entity.id],
                    entity.id,
                )
            )
    return findings


def find_reserved_tag_issues(index: ContentIndex) -> list[Finding]:
    """Flag content tags that claim the engine's reserved tag categories."""
    findings: list[Finding] = []
    for entity in index.entities.values():
        for category in entity.tags.values():
            # Evennia stores tag categories stripped and lowercased, so compare
            # that way against the reserved ones.
            if str(category).strip().lower() in RESERVED_TAG_CATEGORIES:
                findings.append(
                    Finding(
                        "error",
                        "reserved-tag-category",
                        f"tag category '{category}' is reserved by the engine",
                        index.entity_sources[entity.id],
                        entity.id,
                    )
                )
    return findings


def find_location_cycle_issues(index: ContentIndex) -> list[Finding]:
    """Flag objects whose location refs form a placement cycle."""
    edges: dict[str, str] = {}
    refs: dict[str, str] = {}
    for entity in index.entities.values():
        if isinstance(entity, ObjectEntity) and entity.location:
            target = ref_target(entity.location)
            if target in index.entities:
                edges[entity.id] = target
                refs[entity.id] = entity.location
    state: dict[str, str] = {}
    in_cycle: set[str] = set()
    for start in edges:
        if start in state:
            continue
        stack: list[str] = []
        node: str | None = start
        while node is not None and node not in state:
            state[node] = "visiting"
            stack.append(node)
            node = edges.get(node)
        if node is not None and state.get(node) == "visiting":
            # A back edge: the stack from the revisited node onward is the cycle.
            in_cycle.update(stack[stack.index(node) :])
        for seen in stack:
            state[seen] = "done"
    return [
        Finding(
            "error",
            "location-cycle",
            f"location ref '{refs[entity_id]}' forms a placement cycle",
            index.entity_sources[entity_id],
            entity_id,
        )
        for entity_id in refs
        if entity_id in in_cycle
    ]


def find_prototype_ref_issues(index: ContentIndex) -> list[Finding]:
    """Check that `prototype:` refs point at declared prototype entities."""
    findings: list[Finding] = []
    for entity in index.entities.values():
        if not isinstance(entity, ObjectEntity) or not entity.prototype:
            continue
        target = index.entities.get(ref_target(entity.prototype))
        if target is None:
            findings.append(
                Finding(
                    "error",
                    "prototype-not-found",
                    (
                        f"prototype ref '{entity.prototype}' "
                        "does not match any declared entity"
                    ),
                    index.entity_sources[entity.id],
                    entity.id,
                )
            )
        elif not isinstance(target, PrototypeEntity):
            findings.append(
                Finding(
                    "error",
                    "prototype-not-a-template",
                    f"prototype ref '{entity.prototype}' is not a prototype entity",
                    index.entity_sources[entity.id],
                    entity.id,
                )
            )
    return findings


def _iter_strings(value: Any) -> Iterator[str]:
    """Yield every string inside a nested list/dict structure."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_strings(item)


def _refs_of(
    entity: EntityBase,
) -> list[tuple[str, str, tuple[type[EntityBase], ...], str]]:
    """Return `(ref, field-name, allowed entity classes, finding code)` entries.

    Prototypes are rejected everywhere: they are never live objects. Exits are
    links, not containers.
    """
    if isinstance(entity, ExitEntity):
        return [
            (entity.location, "location", (RoomEntity,), "location-not-room"),
            (entity.destination, "destination", (RoomEntity,), "destination-not-room"),
        ]
    if isinstance(entity, ObjectEntity):
        refs: list[tuple[str, str, tuple[type[EntityBase], ...], str]] = []
        if entity.location:
            refs.append(
                (
                    entity.location,
                    "location",
                    (RoomEntity, ObjectEntity),
                    "location-not-room-or-object",
                )
            )
        if entity.home:
            refs.append(
                (
                    entity.home,
                    "home",
                    (RoomEntity, ObjectEntity),
                    "home-not-room-or-object",
                )
            )
        return refs
    return []
