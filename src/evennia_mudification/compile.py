"""Compile raw YAML documents into an indexed content collection."""

from __future__ import annotations

from dataclasses import dataclass, field

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


def compile_documents(documents: list[SourceDocument]) -> ContentIndex:
    """Parse and structurally validate every document; never raises for bad content."""
    index = ContentIndex()
    for document in documents:
        source = str(document.path)
        index.sources.append(source)
        try:
            raw = yaml.safe_load(document.text)
        except yaml.YAMLError as err:
            index.findings.append(Finding("error", "yaml-parse", str(err), source))
            continue
        if raw is None:
            continue
        try:
            bundle = Bundle.model_validate(raw)
        except ValidationError as err:
            for error in err.errors():
                location = ".".join(str(part) for part in error["loc"])
                index.findings.append(
                    Finding("error", "schema", f"{location}: {error['msg']}", source)
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


def _flatten_contents(index: ContentIndex) -> None:
    """Move nested children into the index, injecting `location: @parent`."""

    def walk(parent_id: str, children: list[Entity], source: str) -> None:
        for child in children:
            if not isinstance(child, ObjectEntity):
                index.findings.append(
                    Finding(
                        "error",
                        "nested-kind",
                        f"nested child '{child.id}' must be an object",
                        source,
                        child.id,
                    )
                )
                continue
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
                index.findings.append(
                    Finding(
                        "error",
                        "duplicate-id",
                        f"id '{child.id}' is already defined",
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
