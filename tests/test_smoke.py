"""Tests for the entry point."""

import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from main import main

SRC = Path(__file__).resolve().parent.parent / "src"


def test_main_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    """`main` writes the greeting to stdout."""
    main()
    assert "evennia-mudification" in capsys.readouterr().out


def test_module_is_runnable(capsys: pytest.CaptureFixture[str]) -> None:
    """`python -m main` reaches `main`, covering the `__main__` guard.

    The `sys.modules` eviction is required: importing `main` at the top of this
    file leaves the module cached, and `run_module` then warns that it was
    already imported "prior to execution".
    """
    sys.modules.pop("main", None)
    runpy.run_module("main", run_name="__main__")
    assert "evennia-mudification" in capsys.readouterr().out


def test_entry_point_works_as_a_real_command() -> None:
    """The documented command works in a fresh interpreter.

    The two tests above run inside pytest and inherit the `pythonpath` it
    applied, so they would pass even if a real invocation could not find the
    module. Only a subprocess can catch that.
    """
    result = subprocess.run(
        [sys.executable, "-m", "main"],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": str(SRC)},
    )
    assert "evennia-mudification" in result.stdout
