"""Tests for the Evennia-dependent validation checks."""

from pathlib import Path

from evennia_mudification.compile import ContentIndex, compile_documents
from evennia_mudification.source import LocalDirectorySource
from evennia_mudification.validate import validate_index

REQUIRED = "schema_version: 1\nentities:\n  - id: a\n    kind: room\n    key: a\n"


def _index(tmp_path: Path, extra: str) -> ContentIndex:
    (tmp_path / "c.yaml").write_text(REQUIRED + extra)
    return compile_documents(LocalDirectorySource(tmp_path).documents())


def test_known_protfunc_passes(tmp_path: Path) -> None:
    from evennia.prototypes.prototypes import FUNC_PARSER

    assert "randint" in FUNC_PARSER.callables
    index = _index(
        tmp_path,
        "  - id: b\n    kind: object\n    key: b\n"
        '    attrs:\n      roll: "$randint(1,6)"\n',
    )
    assert validate_index(index, check_evennia=True) == []


def test_unknown_protfunc_is_error(tmp_path: Path) -> None:
    index = _index(
        tmp_path,
        "  - id: b\n    kind: object\n    key: b\n"
        '    attrs:\n      roll: "$definitely_not_a_protfunc(1)"\n',
    )
    findings = validate_index(index, check_evennia=True)
    assert [finding.code for finding in findings] == ["unknown-protfunc"]


def test_invalid_lockstring_is_error(tmp_path: Path) -> None:
    index = _index(
        tmp_path,
        '  - id: b\n    kind: object\n    key: b\n    locks:\n      get: "false("\n',
    )
    findings = validate_index(index, check_evennia=True)
    assert [finding.code for finding in findings] == ["invalid-lock"]


def test_valid_lockstring_passes(tmp_path: Path) -> None:
    index = _index(
        tmp_path,
        '  - id: b\n    kind: object\n    key: b\n    locks:\n      get: "false()"\n',
    )
    assert validate_index(index, check_evennia=True) == []


def test_unresolvable_typeclass(tmp_path: Path) -> None:
    index = _index(
        tmp_path,
        "  - id: b\n    kind: object\n    key: b\n"
        "    typeclass: typeclasses.nope.Missing\n",
    )
    findings = validate_index(index, check_evennia=True)
    assert [finding.code for finding in findings] == ["typeclass-unresolved"]
    assert findings[0].severity == "error"
    relaxed = validate_index(index, check_evennia=True, typeclass_severity="warning")
    assert [finding.severity for finding in relaxed] == ["warning"]


def test_checks_skipped_without_evennia(tmp_path: Path) -> None:
    index = _index(
        tmp_path,
        "  - id: b\n    kind: object\n    key: b\n"
        '    attrs:\n      roll: "$definitely_not_a_protfunc(1)"\n',
    )
    assert validate_index(index) == []
