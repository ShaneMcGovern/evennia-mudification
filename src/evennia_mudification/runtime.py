"""Server-start validation and shared engine state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from evennia.utils import logger

from evennia_mudification.findings import Finding
from evennia_mudification.loading import load_content


@dataclass
class ValidationSummary:
    """What the last content validation found."""

    content_path: str
    entity_count: int
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)


LAST_VALIDATION: ValidationSummary | None = None


def validate_on_start() -> ValidationSummary | None:
    """Load and validate content on server start; never mutates the world.

    Called from `server/conf/at_server_startstop.py::at_server_start`.
    """
    global LAST_VALIDATION
    content_path = getattr(settings, "MUDIFICATION_CONTENT_PATH", None)
    if not content_path:
        logger.log_info(
            "mudification: MUDIFICATION_CONTENT_PATH is not set; "
            "skipping content validation"
        )
        return None
    index, findings = load_content(Path(content_path), check_evennia=True)
    summary = ValidationSummary(
        content_path=str(content_path),
        entity_count=len(index.entities),
        errors=[finding for finding in findings if finding.severity == "error"],
        warnings=[finding for finding in findings if finding.severity == "warning"],
    )
    for finding in summary.errors:
        if finding.code == "load-error":
            # Keep the pre-helper log line for load failures.
            logger.log_err(f"mudification: content load failed: {finding.message}")
        else:
            logger.log_err(f"mudification: {finding.render()}")
    for finding in summary.warnings:
        logger.log_info(f"mudification: {finding.render()}")
    logger.log_info(
        f"mudification: validated {summary.entity_count} entities from "
        f"{summary.content_path} ({len(summary.errors)} errors)"
    )
    LAST_VALIDATION = summary
    return summary
