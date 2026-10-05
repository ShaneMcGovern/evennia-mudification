"""Tests for structural validation."""

from pathlib import Path

from evennia_mudification.compile import compile_documents
from evennia_mudification.findings import Finding
from evennia_mudification.source import LocalDirectorySource
from evennia_mudification.validate import validate_index

CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "basic"


def _validate_dir(root: Path) -> list[Finding]:
    index = compile_documents(LocalDirectorySource(root).documents())
    assert index.findings == []
    return validate_index(index)


def test_valid_corpus_has_no_findings() -> None:
    assert _validate_dir(CORPUS) == []


def test_dangling_ref_is_error(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n  - id: a\n"
        '    kind: object\n    key: x\n    location: "@nope"\n'
    )
    findings = _validate_dir(tmp_path)
    assert [finding.code for finding in findings] == ["dangling-ref"]
    assert "@nope" in findings[0].message


def test_destination_must_be_room(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: a\n    kind: room\n    key: a\n"
        "  - id: b\n    kind: object\n    key: b\n"
        "  - id: c\n    kind: exit\n    key: c\n"
        '    location: "@a"\n    destination: "@b"\n'
    )
    findings = _validate_dir(tmp_path)
    assert [finding.code for finding in findings] == ["destination-not-room"]


def test_exit_location_must_be_room(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: a\n    kind: room\n    key: a\n"
        "  - id: b\n    kind: object\n    key: b\n"
        "  - id: c\n    kind: exit\n    key: c\n"
        '    location: "@b"\n    destination: "@a"\n'
    )
    findings = _validate_dir(tmp_path)
    assert [finding.code for finding in findings] == ["location-not-room"]
