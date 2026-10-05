"""Tests for content sources."""

from pathlib import Path

from evennia_mudification.source import LocalDirectorySource


def test_reads_yaml_files_sorted(tmp_path: Path) -> None:
    (tmp_path / "b.yaml").write_text("b: 1\n", encoding="utf-8")
    (tmp_path / "a.yaml").write_text("a: 1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore me\n", encoding="utf-8")
    nested = tmp_path / "zones"
    nested.mkdir()
    (nested / "c.yaml").write_text("c: 1\n", encoding="utf-8")

    documents = LocalDirectorySource(tmp_path).documents()

    assert [document.path.name for document in documents] == [
        "a.yaml",
        "b.yaml",
        "c.yaml",
    ]
    assert documents[0].text == "a: 1\n"


def test_missing_root_yields_no_documents(tmp_path: Path) -> None:
    assert LocalDirectorySource(tmp_path / "does-not-exist").documents() == []
