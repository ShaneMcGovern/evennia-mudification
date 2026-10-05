"""Compile raw YAML documents into an indexed content collection."""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml
from pydantic import ValidationError

from evennia_mudification.findings import Finding
from evennia_mudification.models import Bundle, Entity
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
    return index
