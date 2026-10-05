"""Server-start validation and shared engine state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings
from evennia.utils import logger

from evennia_mudification.findings import Finding
from evennia_mudification.loading import load_content
from evennia_mudification.proto import register_prototypes


@dataclass
class ValidationSummary:
    """What the last content validation found."""

    content_path: str
    entity_count: int
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)


LAST_VALIDATION: ValidationSummary | None = None
LAST_APPLIED: int | None = None


def _connected_sessions() -> list[Any]:
    """The live sessions, or none when no server is running.

    `SESSION_HANDLER` is `None` outside a server process (pytest included),
    and startup validation may never raise, so that case is empty, not an
    error.
    """
    from evennia.server.sessionhandler import SESSION_HANDLER

    if SESSION_HANDLER is None:
        return []
    return list(SESSION_HANDLER.get_sessions())


def notify_connected_superusers(summary: ValidationSummary) -> int:
    """Message connected superusers/admins about validation findings.

    Returns the number of accounts notified. Each account is messaged at most
    once even when it holds several sessions, because ``account.msg`` already
    relays to every session that account has. Best effort: sessions without
    accounts are skipped, and messaging failures never raise.
    """
    lines = [
        f"mudification: validated {summary.entity_count} entities from "
        f"{summary.content_path} ({len(summary.errors)} errors, "
        f"{len(summary.warnings)} warnings)"
    ]
    lines.extend(finding.render() for finding in [*summary.errors, *summary.warnings])
    text = "\n".join(lines)
    notified = 0
    seen: set[Any] = set()
    for session in _connected_sessions():
        account = getattr(session, "account", None)
        if account is None:
            continue
        account_id = getattr(account, "pk", None)
        key = account_id if account_id is not None else id(account)
        if key in seen:
            continue
        seen.add(key)
        if getattr(account, "is_superuser", False) or account.permissions.check(
            "Admin"
        ):
            try:
                account.msg(text)
                notified += 1
            except Exception:
                continue
    return notified


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
            logger.log_err(f"mudification: content load failed: {finding.message}")
        else:
            logger.log_err(f"mudification: {finding.render()}")
    for finding in summary.warnings:
        logger.log_info(f"mudification: {finding.render()}")
    registered = 0 if summary.errors else register_prototypes(index)
    logger.log_info(
        f"mudification: validated {summary.entity_count} entities from "
        f"{summary.content_path} ({len(summary.errors)} errors, "
        f"{registered} templates registered)"
    )
    LAST_VALIDATION = summary
    if summary.errors or summary.warnings:
        notify_connected_superusers(summary)
    return summary
