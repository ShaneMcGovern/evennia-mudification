"""Tests for the compiler."""

from pathlib import Path

from evennia_mudification.compile import compile_documents
from evennia_mudification.source import LocalDirectorySource

CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "basic"


def test_compiles_valid_corpus() -> None:
    index = compile_documents(LocalDirectorySource(CORPUS).documents())
    assert set(index.entities) == {"square", "inn", "square-inn", "signpost"}
    assert index.findings == []
    assert index.entity_sources["square"].endswith("village.yaml")


def test_duplicate_id_reports_both_files(tmp_path: Path) -> None:
    one = tmp_path / "one.yaml"
    one.write_text(
        "schema_version: 1\nentities:\n  - id: dup\n    kind: room\n    key: one\n"
    )
    two = tmp_path / "two.yaml"
    two.write_text(
        "schema_version: 1\nentities:\n  - id: dup\n    kind: room\n    key: two\n"
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    codes = [finding.code for finding in index.findings]
    assert "duplicate-id" in codes
    duplicate = next(f for f in index.findings if f.code == "duplicate-id")
    assert "one.yaml" in duplicate.message
    assert "two.yaml" in duplicate.source


def test_invalid_yaml_reports_parse_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("entities: [unclosed\n")
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert [finding.code for finding in index.findings] == ["yaml-parse"]


def test_schema_error_reports_field_location(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "schema_version: 1\nentities:\n  - id: room\n"
        "    kind: room\n    key: x\n    locaton: y\n"
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    finding = index.findings[0]
    assert finding.code == "schema"
    assert "locaton" in finding.message


def test_empty_file_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "empty.yaml").write_text("")
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert index.entities == {}
    assert index.findings == []
