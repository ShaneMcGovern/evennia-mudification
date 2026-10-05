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


def test_reserved_tag_category_is_error(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: a\n    kind: room\n    key: a\n    tags: {zone: mudification}\n"
    )
    findings = _validate_dir(tmp_path)
    assert [finding.code for finding in findings] == ["reserved-tag-category"]


def test_reserved_tag_category_check_is_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: a\n    kind: room\n    key: a\n    tags: {zone: Mudification}\n"
    )
    findings = _validate_dir(tmp_path)
    assert [finding.code for finding in findings] == ["reserved-tag-category"]


def test_reserved_tag_category_check_ignores_padding(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: a\n    kind: room\n    key: a\n"
        "    tags: {zone: ' mudification_source '}\n"
    )
    findings = _validate_dir(tmp_path)
    assert [finding.code for finding in findings] == ["reserved-tag-category"]


def test_prototype_ref_must_resolve_to_template(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        '  - id: g\n    kind: object\n    key: g\n    prototype: "@missing"\n'
    )
    findings = _validate_dir(tmp_path)
    assert [finding.code for finding in findings] == ["prototype-not-found"]


def test_prototype_ref_to_non_template_is_error(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: other\n    kind: object\n    key: other\n"
        '  - id: g\n    kind: object\n    key: g\n    prototype: "@other"\n'
    )
    findings = _validate_dir(tmp_path)
    assert [finding.code for finding in findings] == ["prototype-not-a-template"]


def test_ref_to_counted_base_is_dangling(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: hall\n    kind: room\n    key: hall\n"
        "  - id: rats\n    kind: object\n    key: rats\n    count: 2\n"
        '  - id: marker\n    kind: object\n    key: marker\n    location: "@rats"\n'
    )
    findings = _validate_dir(tmp_path)
    assert [finding.code for finding in findings] == ["dangling-ref"]
    assert "@rats" in findings[0].message
