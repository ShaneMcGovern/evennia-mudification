"""Shared content loading: one guarded compile-and-validate path."""

from __future__ import annotations

from pathlib import Path

from evennia_mudification.compile import ContentIndex, compile_documents
from evennia_mudification.findings import Finding, Severity
from evennia_mudification.source import LocalDirectorySource
from evennia_mudification.validate import validate_index


def load_content(
    root: Path,
    *,
    check_evennia: bool = True,
    typeclass_severity: Severity = "error",
) -> tuple[ContentIndex, list[Finding]]:
    """Load, compile and validate a content root; never raises for bad content.

    A missing root is the ``content-root-missing`` error, so a typo'd path
    cannot validate zero entities clean. Read failures and any other exception
    become a synthetic ``load-error`` finding instead of aborting the CLI, the
    in-game command or the server-start hook.
    """
    if not root.is_dir():
        finding = Finding(
            "error",
            "content-root-missing",
            f"content root '{root}' does not exist or is not a directory",
            str(root),
        )
        return ContentIndex(), [finding]
    try:
        index = compile_documents(LocalDirectorySource(root).documents())
        findings = index.findings + validate_index(
            index, check_evennia=check_evennia, typeclass_severity=typeclass_severity
        )
    except Exception as err:
        return ContentIndex(), [Finding("error", "load-error", str(err), str(root))]
    return index, findings
