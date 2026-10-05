"""Validation for a compiled content index."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from evennia_mudification.compile import ContentIndex
from evennia_mudification.findings import Finding, Severity
from evennia_mudification.models import (
    EntityBase,
    ExitEntity,
    ObjectEntity,
    RoomEntity,
    ref_target,
)

_RE_PROTFUNC = re.compile(r"(?<!\$)\$([a-z_][a-z0-9_]*)\(")


def validate_index(
    index: ContentIndex,
    *,
    check_evennia: bool = False,
    typeclass_severity: Severity = "error",
) -> list[Finding]:
    """Check references and kind constraints; collects every problem found."""
    findings: list[Finding] = []
    for entity in index.entities.values():
        source = index.entity_sources[entity.id]
        for ref, field_name in _refs_of(entity):
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
            if isinstance(entity, ExitEntity) and not isinstance(target, RoomEntity):
                findings.append(
                    Finding(
                        "error",
                        f"{field_name}-not-room",
                        f"{field_name} '{ref}' is not a room",
                        source,
                        entity.id,
                    )
                )
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
    from evennia.utils.utils import class_from_module

    findings: list[Finding] = []
    for entity in index.entities.values():
        if not entity.typeclass:
            continue
        try:
            class_from_module(entity.typeclass)
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


def _refs_of(entity: EntityBase) -> list[tuple[str, str]]:
    """Return `(ref, field-name)` pairs declared on an entity."""
    refs: list[tuple[str, str]] = []
    if isinstance(entity, ExitEntity):
        refs.append((entity.location, "location"))
        refs.append((entity.destination, "destination"))
    elif isinstance(entity, ObjectEntity):
        if entity.location:
            refs.append((entity.location, "location"))
        if entity.home:
            refs.append((entity.home, "home"))
    return refs
