"""Check the declared Evennia floor against the runtime check."""

import tomllib
from pathlib import Path

import pytest

from evennia_mudification import runtime

ROOT = Path(__file__).resolve().parents[1]


def test_an_older_evennia_is_refused() -> None:
    with pytest.raises(RuntimeError, match=r"6\.1 or later"):
        runtime._check_evennia_version("6.0.9")


def test_the_supported_floor_passes() -> None:
    runtime._check_evennia_version("6.1.0")
    runtime._check_evennia_version("6.2")


def test_an_unparseable_version_is_ignored() -> None:
    runtime._check_evennia_version("dev")
    runtime._check_evennia_version(None)


def test_the_declared_extra_matches_the_runtime_floor() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    (declaration,) = project["optional-dependencies"]["evennia"]
    name, _, floor = declaration.partition(">=")
    assert name == "evennia"
    declared = tuple(int(part) for part in floor.split(".")[:2])
    assert declared == runtime._MINIMUM_EVENNIA
