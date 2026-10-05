"""Tests for the mudification CLI."""

import json
import os
import runpy
import sys
from pathlib import Path

import pytest

from evennia_mudification.cli import main

CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "basic"


def test_validate_clean_corpus(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(CORPUS)]) == 0
    assert "4 entities, 0 errors, 0 warnings" in capsys.readouterr().out


def test_validate_reports_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n  - id: a\n    kind: object\n"
        '    key: x\n    location: "@nope"\n'
    )
    assert main(["validate", str(tmp_path)]) == 1
    assert "dangling-ref" in capsys.readouterr().out


def test_validate_non_utf8_file_reports_load_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "broken.yaml").write_bytes(b"\xff\xfe\x00")
    assert main(["validate", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "load-error" in out


def test_validate_missing_root_is_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "does-not-exist"
    assert main(["validate", str(missing)]) == 1
    out = capsys.readouterr().out
    assert "content-root-missing" in out
    assert str(missing) in out


def test_validate_relative_path_survives_evennia_chdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Evennia's settings import chdirs outside a game dir; resolve first."""
    corpus = tmp_path / "content"
    corpus.mkdir()
    (corpus / "c.yaml").write_text(
        "schema_version: 1\nentities:\n  - id: a\n    kind: room\n    key: a\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    def chdir_away() -> bool:
        os.chdir("/")
        return False

    monkeypatch.setattr("evennia_mudification.cli._ensure_evennia", chdir_away)
    assert main(["validate", "content"]) == 0
    assert "1 entities, 0 errors, 0 warnings" in capsys.readouterr().out


def test_validate_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n  - id: a\n    kind: object\n"
        '    key: x\n    location: "@nope"\n'
    )
    assert main(["validate", "--json", str(tmp_path)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["code"] == "dangling-ref"


def test_schema_prints(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema"]) == 0
    assert "$schema" in capsys.readouterr().out


def test_schema_writes(tmp_path: Path) -> None:
    target = tmp_path / "out" / "schema.json"
    assert main(["schema", "--write", str(target)]) == 0
    assert (
        json.loads(target.read_text(encoding="utf-8"))["title"]
        == "Mudification content bundle"
    )


def test_module_entrypoint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["mudification", "schema"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("evennia_mudification", run_name="__main__")
    assert excinfo.value.code == 0
