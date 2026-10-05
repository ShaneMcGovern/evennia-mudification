"""Tests for the in-game command and server-start validation."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

from evennia.prototypes import spawner
from evennia.utils import create
from evennia.utils.test_resources import BaseEvenniaTestCase

from evennia_mudification import deferred, runtime
from evennia_mudification.commands import CmdMudification
from evennia_mudification.identity import find_entity_object

CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "basic"

DANGLING = (
    "schema_version: 1\nentities:\n  - id: a\n"
    '    kind: object\n    key: x\n    location: "@nope"\n'
)


def _write_dangling(directory: str) -> None:
    """Write content whose only entity references an undeclared one."""
    Path(directory, "c.yaml").write_text(DANGLING, encoding="utf-8")


def test_validate_on_start_importable_from_package() -> None:
    from evennia_mudification import validate_on_start

    assert validate_on_start is runtime.validate_on_start


def test_package_import_needs_no_django_settings() -> None:
    """The CLI imports the package before it configures Django; keep that working."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "DJANGO_SETTINGS_MODULE"
    }
    result = subprocess.run(
        [sys.executable, "-c", "import evennia_mudification"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr


class TestCmdMudification(BaseEvenniaTestCase):
    def _settings(self) -> Any:
        return self.settings(MUDIFICATION_CONTENT_PATH=str(CORPUS))

    def _caller(self) -> Any:
        return create.create_object(
            "evennia.objects.objects.DefaultCharacter", key="Caller"
        )

    def _run(self, caller: Any, args: str) -> str:
        output: list[str] = []
        cmd = CmdMudification()
        cmd.caller = caller
        cmd.args = args
        cmd.msg = lambda text=None, **kwargs: output.append(str(text))
        cmd.func()
        return "\n".join(output)

    def test_plan_apply_lifecycle(self) -> None:
        caller = self._caller()
        with self._settings():
            output = self._run(caller, "plan")
            assert "create square" in output
            output = self._run(caller, "apply")
            assert "apply confirm" in output
            output = self._run(caller, "apply confirm")
            assert "create square: ok" in output
            output = self._run(caller, "plan")
            assert "no changes" in output

    def test_apply_when_in_sync_reports_no_changes(self) -> None:
        caller = self._caller()
        with self._settings():
            self._run(caller, "apply confirm")
            output = self._run(caller, "apply")
        assert "no changes" in output

    def test_apply_refuses_invalid_content(self) -> None:
        # A unittest.TestCase cannot take pytest's tmp_path fixture; the temp
        # directory stands in for a broken content checkout.
        with tempfile.TemporaryDirectory() as directory:
            _write_dangling(directory)
            with self.settings(MUDIFICATION_CONTENT_PATH=directory):
                output = self._run(self._caller(), "apply")
        assert "nothing was applied" in output

    def test_plan_refuses_invalid_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _write_dangling(directory)
            with self.settings(MUDIFICATION_CONTENT_PATH=directory):
                output = self._run(self._caller(), "plan")
        assert "nothing was applied" in output

    def test_validate_rejects_dangling_ref(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _write_dangling(directory)
            with self.settings(MUDIFICATION_CONTENT_PATH=directory):
                output = self._run(self._caller(), "validate")
        assert "dangling-ref" in output

    def test_load_registers_prototypes(self) -> None:
        caller = self._caller()
        with (
            self._settings(),
            mock.patch(
                "evennia_mudification.commands.register_prototypes", return_value=0
            ) as mocked,
        ):
            self._run(caller, "validate")
        assert mocked.call_count == 1

    def test_missing_content_path(self) -> None:
        with self.settings(MUDIFICATION_CONTENT_PATH=None):
            output = self._run(self._caller(), "validate")
        assert "MUDIFICATION_CONTENT_PATH is not set." in output

    def test_load_failure_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "broken.yaml").write_bytes(b"\xff\xfe\x00")
            with self.settings(MUDIFICATION_CONTENT_PATH=directory):
                output = self._run(self._caller(), "validate")
        assert "content load failed" in output

    def test_missing_content_root_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "does-not-exist"
            with self.settings(MUDIFICATION_CONTENT_PATH=str(missing)):
                output = self._run(self._caller(), "validate")
        assert "content-root-missing" in output
        assert str(missing) in output

    def test_unknown_subcommand(self) -> None:
        with self._settings():
            output = self._run(self._caller(), "bogus")
        assert "unknown subcommand" in output

    def test_apply_reports_per_entity_failures(self) -> None:
        caller = self._caller()
        with (
            self._settings(),
            mock.patch.object(spawner, "spawn", side_effect=RuntimeError("boom")),
        ):
            output = self._run(caller, "apply confirm")
        assert "some entities failed" in output

    def test_status_before_validation(self) -> None:
        with self._settings(), mock.patch.object(runtime, "LAST_VALIDATION", None):
            output = self._run(self._caller(), "status")
        assert "no validation has run yet" in output
        assert "managed entities in the database: 0" in output

    def test_default_subcommand_is_status(self) -> None:
        with self._settings():
            output = self._run(self._caller(), "")
        assert "managed entities in the database: 0" in output

    def test_status_after_validation(self) -> None:
        caller = self._caller()
        with self._settings():
            self._run(caller, "validate")
            output = self._run(caller, "status")
        assert "4 entities" in output
        assert "managed entities in the database: 0" in output

    def test_status_reports_last_applied_after_apply(self) -> None:
        caller = self._caller()
        with self._settings(), mock.patch.object(runtime, "LAST_APPLIED", None):
            before = self._run(caller, "status")
            assert "last applied" not in before
            self._run(caller, "apply confirm")
            after = self._run(caller, "status")
            assert "last applied: 4 entities" in after

    def test_apply_deferred_when_reactor_running(self) -> None:
        caller = self._caller()
        with (
            self._settings(),
            mock.patch.object(deferred, "_reactor_running", return_value=True),
            mock.patch("evennia.utils.utils.run_async") as run_async_mock,
        ):
            output = self._run(caller, "apply confirm")
        assert "applying off-thread" in output
        assert run_async_mock.call_count == 1

    def test_prune_reports_then_confirms(self) -> None:
        caller = self._caller()
        with self._settings():
            self._run(caller, "apply confirm")
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "c.yaml").write_text(
                "schema_version: 1\nentities:\n"
                "  - id: inn\n    kind: room\n    key: The Wayfarer's Inn\n",
                encoding="utf-8",
            )
            with self.settings(MUDIFICATION_CONTENT_PATH=directory):
                output = self._run(caller, "prune")
                assert "retire square" in output
                assert "prune confirm" in output
                assert find_entity_object("square") is not None  # preview only
                output = self._run(caller, "prune confirm")
        assert "destroy square: ok" in output
        assert "destroy signpost: ok" in output

    def test_prune_with_nothing_to_retire(self) -> None:
        caller = self._caller()
        with self._settings():
            self._run(caller, "apply confirm")
            output = self._run(caller, "prune")
        assert "no retirements" in output

    def test_status_reports_retirements_and_sources(self) -> None:
        caller = self._caller()
        with self._settings():
            self._run(caller, "validate")
            output = self._run(caller, "status")
        assert "retirements: 0" in output
        assert "source bundles: 1" in output


class TestValidateOnStart(BaseEvenniaTestCase):
    def test_records_summary(self) -> None:
        with self.settings(MUDIFICATION_CONTENT_PATH=str(CORPUS)):
            summary = runtime.validate_on_start()
        assert summary is not None
        assert summary.entity_count == 4
        assert summary.errors == []
        assert runtime.LAST_VALIDATION is summary

    def test_records_errors_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            _write_dangling(directory)
            with self.settings(MUDIFICATION_CONTENT_PATH=directory):
                summary = runtime.validate_on_start()
        assert summary is not None
        assert summary.entity_count == 1
        assert [finding.code for finding in summary.errors] == ["dangling-ref"]
        assert summary.warnings == []
        assert runtime.LAST_VALIDATION is summary

    def test_records_load_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "broken.yaml").write_bytes(b"\xff\xfe\x00")
            with self.settings(MUDIFICATION_CONTENT_PATH=directory):
                summary = runtime.validate_on_start()
        assert summary is not None
        assert summary.entity_count == 0
        assert [finding.code for finding in summary.errors] == ["load-error"]
        assert runtime.LAST_VALIDATION is summary

    def test_records_missing_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "does-not-exist"
            with self.settings(MUDIFICATION_CONTENT_PATH=str(missing)):
                summary = runtime.validate_on_start()
        assert summary is not None
        assert summary.entity_count == 0
        assert [finding.code for finding in summary.errors] == ["content-root-missing"]
        assert runtime.LAST_VALIDATION is summary

    def test_unset_path_returns_none(self) -> None:
        with self.settings(MUDIFICATION_CONTENT_PATH=None):
            assert runtime.validate_on_start() is None
