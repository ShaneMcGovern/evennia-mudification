"""The `mudification` command-line interface."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path

from evennia_mudification.findings import Finding
from evennia_mudification.loading import load_content
from evennia_mudification.schema import (
    SCHEMA_PATH,
    generate_json_schema,
    write_schema,
)


def _package_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("evennia-mudification")
    except PackageNotFoundError:  # pragma: no cover - only when not installed
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(prog="mudification")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_package_version()}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate", help="validate a content directory"
    )
    validate_parser.add_argument(
        "path",
        nargs="?",
        # An empty variable is a set-but-blank environment; fall back rather
        # than validating the working directory.
        default=os.environ.get("MUDIFICATION_CONTENT_PATH") or "content",
        help="content root (default: $MUDIFICATION_CONTENT_PATH or ./content)",
    )
    validate_parser.add_argument(
        "--json", action="store_true", help="emit findings as JSON"
    )

    schema_parser = subparsers.add_parser(
        "schema", help="print or write the JSON Schema artifact"
    )
    schema_parser.add_argument(
        "--write",
        nargs="?",
        const=str(SCHEMA_PATH),
        default=None,
        metavar="PATH",
        help=f"write the schema to PATH (default: {SCHEMA_PATH})",
    )

    args = parser.parse_args(argv)

    if args.command == "validate":
        return _validate(Path(args.path), as_json=args.json)
    if args.command == "schema":
        if args.write is not None:
            write_schema(Path(args.write))
        else:
            print(json.dumps(generate_json_schema(), indent=2))
        return 0
    return 2  # pragma: no cover - argparse restricts command to known values


def _validate(root: Path, *, as_json: bool) -> int:
    # Resolve before Evennia's settings import: outside a game directory that
    # import chdirs the process towards `/`, which would turn a relative
    # content path into a missing root.
    root = root.resolve()
    evennia_available = _ensure_evennia()
    index, findings = load_content(
        root, check_evennia=evennia_available, typeclass_severity="warning"
    )
    if not evennia_available:
        # A run that skipped the semantic layer must say so in both output
        # modes, or a CI cannot tell "checked and clean" from "not checked".
        findings = [
            Finding(
                "warning",
                "semantic-checks-skipped",
                "Evennia is not importable here; protfunc, lockstring and "
                "typeclass checks did not run",
                str(root),
            ),
            *findings,
        ]
    errors = [finding for finding in findings if finding.severity == "error"]
    if as_json:
        print(
            json.dumps([dataclasses.asdict(finding) for finding in findings], indent=2)
        )
    else:
        for finding in findings:
            print(finding.render())
        print(
            f"{len(index.entities)} entities, {len(errors)} errors, "
            f"{len(findings) - len(errors)} warnings"
        )
    return 1 if errors else 0


def _ensure_evennia() -> bool:
    """Configure Django/Evennia for library use; False when unavailable."""
    try:
        import django

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "evennia.settings_default")
        django.setup()
    except Exception:
        return False
    return True
