"""Tests for the shared content loading helper."""

from pathlib import Path

from evennia_mudification.loading import load_content

CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "basic"


def test_clean_corpus_loads_without_findings() -> None:
    index, findings = load_content(CORPUS)
    assert set(index.entities) == {"square", "inn", "square-inn", "signpost"}
    assert findings == []


def test_non_utf8_file_becomes_load_error(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_bytes(b"\xff\xfe\x00")
    index, findings = load_content(tmp_path)
    assert index.entities == {}
    assert [finding.code for finding in findings] == ["load-error"]
    assert findings[0].severity == "error"
    assert str(tmp_path) in findings[0].source


def test_missing_root_is_an_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    index, findings = load_content(missing)
    assert index.entities == {}
    assert [finding.code for finding in findings] == ["content-root-missing"]
    assert findings[0].severity == "error"
    assert str(missing) in findings[0].message
    assert str(missing) in findings[0].source


def test_file_root_is_an_error(tmp_path: Path) -> None:
    root_file = tmp_path / "content.yaml"
    root_file.write_text("schema_version: 1\nentities: []\n", encoding="utf-8")
    index, findings = load_content(root_file)
    assert index.entities == {}
    assert [finding.code for finding in findings] == ["content-root-missing"]
