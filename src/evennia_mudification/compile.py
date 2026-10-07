"""Compile raw YAML documents into an indexed content collection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import yaml
from pydantic import ValidationError

from evennia_mudification.findings import Finding
from evennia_mudification.models import (
    Bundle,
    Entity,
    ExitEntity,
    ObjectEntity,
    ReverseOverride,
    RoomEntity,
    ref_target,
)
from evennia_mudification.source import SourceDocument


@dataclass
class ContentIndex:
    """Every valid entity by id, where it came from, and accumulated findings."""

    entities: dict[str, Entity] = field(default_factory=dict)
    entity_sources: dict[str, str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    # Synthesized ids (counted instances, reverse exits) mapped to the declared
    # id they were built from.
    derived_ids: dict[str, str] = field(default_factory=dict)


def _error_location(error: Mapping[str, Any], raw: Any) -> str:
    """Render a pydantic error loc without the discriminated-union tag.

    Pydantic inserts the union tag into the loc (`entities.0.room.licks`),
    naming a part the author never wrote; the kind value on the parsed node
    identifies and drops it.
    """
    parts: list[str] = []
    node = raw
    for part in error["loc"]:
        if (
            isinstance(part, str)
            and isinstance(node, dict)
            and node.get("kind") == part
        ):
            continue
        parts.append(str(part))
        if isinstance(part, int) and isinstance(node, list) and part < len(node):
            node = node[part]
        elif isinstance(part, str) and isinstance(node, dict):
            node = node.get(part)
        else:
            node = None
    return ".".join(parts)


def compile_documents(documents: list[SourceDocument]) -> ContentIndex:
    """Parse and structurally validate every document; never raises for bad content."""
    index = ContentIndex()
    for document in documents:
        source = str(document.path)
        index.sources.append(source)
        try:
            raw = yaml.safe_load(document.text)
        except (yaml.YAMLError, RecursionError) as err:
            # PyYAML's recursive loader overflows on pathologically deep
            # nesting; that is content error, not a crash.
            index.findings.append(Finding("error", "yaml-parse", str(err), source))
            continue
        if raw is None:
            # A blanked or comment-only file would otherwise drop every entity
            # it used to hold with no finding explaining the disappearance.
            index.findings.append(
                Finding(
                    "error",
                    "empty-bundle",
                    "file holds no bundle; a bundle needs schema_version and entities",
                    source,
                )
            )
            continue
        try:
            bundle = Bundle.model_validate(raw)
        except ValidationError as err:
            for error in err.errors():
                location = _error_location(error, raw)
                prefix = f"{location}: " if location else ""
                index.findings.append(
                    Finding("error", "schema", f"{prefix}{error['msg']}", source)
                )
            continue
        for entity in bundle.entities:
            if entity.id in index.entities:
                other = index.entity_sources[entity.id]
                index.findings.append(
                    Finding(
                        "error",
                        "duplicate-id",
                        f"id '{entity.id}' is already defined in {other}",
                        source,
                        entity.id,
                    )
                )
                continue
            index.entities[entity.id] = entity
            index.entity_sources[entity.id] = source
    _flatten_contents(index)
    _expand_counts(index)
    _synthesize_reverse_exits(index)
    return index


def _subtree_ids(entities: Sequence[Entity]) -> list[str]:
    """Return every declared id in a nested subtree, depth first."""
    ids: list[str] = []
    for entity in entities:
        ids.append(entity.id)
        if isinstance(entity, (RoomEntity, ObjectEntity)):
            ids.extend(_subtree_ids(entity.contents))
    return ids


def _flatten_contents(index: ContentIndex) -> None:
    """Move nested children into the index, injecting `location: @parent`."""

    def walk(parent_id: str, children: list[ObjectEntity], source: str) -> None:
        for child in children:
            if child.location is not None:
                index.findings.append(
                    Finding(
                        "error",
                        "nested-location",
                        f"nested child '{child.id}' must not declare a location "
                        "(it takes the parent's)",
                        source,
                        child.id,
                    )
                )
                continue
            if child.id in index.entities:
                descendants = _subtree_ids(list(child.contents))
                detail = (
                    f"; its descendants are discarded: {', '.join(descendants)}"
                    if descendants
                    else ""
                )
                index.findings.append(
                    Finding(
                        "error",
                        "duplicate-id",
                        f"id '{child.id}' is already defined{detail}",
                        source,
                        child.id,
                    )
                )
                continue
            if child.count is not None:
                # Counted entities with children are flagged by `_expand_counts`;
                # keeping the children unflattened reports it exactly once.
                index.entities[child.id] = child.model_copy(
                    update={"location": f"@{parent_id}"}
                )
                index.entity_sources[child.id] = source
                continue
            grandchildren = list(child.contents)
            flat = child.model_copy(
                update={"location": f"@{parent_id}", "contents": []}
            )
            index.entities[flat.id] = flat
            index.entity_sources[flat.id] = source
            walk(flat.id, grandchildren, source)

    for entity in list(index.entities.values()):
        if not isinstance(entity, (RoomEntity, ObjectEntity)) or not entity.contents:
            continue
        if isinstance(entity, ObjectEntity) and entity.count is not None:
            # Flagged by `_expand_counts`; leave the children for that report.
            continue
        source = index.entity_sources[entity.id]
        children = list(entity.contents)
        index.entities[entity.id] = entity.model_copy(update={"contents": []})
        walk(entity.id, children, source)


def _expand_counts(index: ContentIndex) -> None:
    """Expand `count: N` objects into `<id>#1..N` instances."""
    for entity in list(index.entities.values()):
        if not isinstance(entity, ObjectEntity) or entity.count is None:
            continue
        source = index.entity_sources[entity.id]
        if entity.contents:
            index.findings.append(
                Finding(
                    "error",
                    "count-with-contents",
                    f"counted entity '{entity.id}' must not declare contents",
                    source,
                    entity.id,
                )
            )
            continue
        del index.entities[entity.id]
        del index.entity_sources[entity.id]
        for ordinal in range(1, entity.count + 1):
            instance = entity.model_copy(
                update={"id": f"{entity.id}#{ordinal}", "count": None}
            )
            index.entities[instance.id] = instance
            index.entity_sources[instance.id] = source
            index.derived_ids[instance.id] = entity.id


def _synthesize_reverse_exits(index: ContentIndex) -> None:
    """Create `<id>:reverse` exits for declared `reverse:` markers."""
    # Synthesized `<id>:reverse` cannot collide: declared ids forbid `:`, source
    # ids are unique, and synthesized copies carry `reverse: None`.
    for entity in list(index.entities.values()):
        if not isinstance(entity, ExitEntity) or not entity.reverse:
            continue
        source = index.entity_sources[entity.id]
        reverse_id = f"{entity.id}:reverse"
        # The reverse leads back where this exit came from, so it swaps
        # location/destination and takes the arrival room's key.
        leads_to = index.entities.get(ref_target(entity.location))
        override = (
            entity.reverse if isinstance(entity.reverse, ReverseOverride) else None
        )
        if override is not None:
            key = override.key or (
                leads_to.key if isinstance(leads_to, RoomEntity) else entity.key
            )
            aliases = list(override.aliases)
        else:
            key = leads_to.key if isinstance(leads_to, RoomEntity) else entity.key
            aliases = []
        reverse = entity.model_copy(
            update={
                "id": reverse_id,
                "location": entity.destination,
                "destination": entity.location,
                "key": key,
                "aliases": aliases,
                "reverse": None,
            }
        )
        index.entities[reverse_id] = reverse
        index.entity_sources[reverse_id] = source
        index.derived_ids[reverse_id] = entity.id
