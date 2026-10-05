"""Tests for notifying connected superusers about startup findings."""

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from evennia.utils.test_resources import BaseEvenniaTestCase

from evennia_mudification import runtime
from evennia_mudification.findings import Finding


class FakePermissions:
    def __init__(self, perms: set[str]) -> None:
        self.perms = perms

    def check(self, *perms: str, **kwargs: object) -> bool:
        return bool(self.perms & set(perms))


def _session(
    is_superuser: bool, perms: set[str], messages: list[str]
) -> SimpleNamespace:
    account = SimpleNamespace(
        is_superuser=is_superuser,
        permissions=FakePermissions(perms),
        msg=messages.append,
    )
    return SimpleNamespace(account=account)


class TestConnectedSessions(BaseEvenniaTestCase):
    def test_reads_the_session_handler(self) -> None:
        fake = SimpleNamespace(get_sessions=lambda **kwargs: [1, 2])
        with mock.patch("evennia.server.sessionhandler.SESSION_HANDLER", fake):
            assert runtime._connected_sessions() == [1, 2]

    def test_without_a_server_it_is_empty(self) -> None:
        # SESSION_HANDLER is None outside a running server (pytest included).
        with mock.patch("evennia.server.sessionhandler.SESSION_HANDLER", None):
            assert runtime._connected_sessions() == []


class TestNotify(BaseEvenniaTestCase):
    def test_messages_only_staff_and_returns_count(self) -> None:
        staff_messages: list[str] = []
        player_messages: list[str] = []
        sessions = [
            _session(True, set(), staff_messages),
            _session(False, {"Admin"}, staff_messages),
            _session(False, {"Player"}, player_messages),
            SimpleNamespace(account=None),
        ]
        summary = runtime.ValidationSummary(
            content_path="x", entity_count=1, errors=[Finding("error", "c", "m", "x")]
        )
        with mock.patch.object(runtime, "_connected_sessions", return_value=sessions):
            assert runtime.notify_connected_superusers(summary) == 2
        assert len(staff_messages) == 2
        assert player_messages == []
        assert "mudification" in staff_messages[0]

    def test_no_sessions_is_quiet(self) -> None:
        summary = runtime.ValidationSummary(content_path="x", entity_count=0)
        with mock.patch.object(runtime, "_connected_sessions", return_value=[]):
            assert runtime.notify_connected_superusers(summary) == 0

    def test_account_with_several_sessions_is_notified_once(self) -> None:
        messages: list[str] = []
        account = SimpleNamespace(
            is_superuser=True,
            permissions=FakePermissions(set()),
            msg=messages.append,
        )
        sessions = [SimpleNamespace(account=account), SimpleNamespace(account=account)]
        summary = runtime.ValidationSummary(content_path="x", entity_count=0)
        with mock.patch.object(runtime, "_connected_sessions", return_value=sessions):
            assert runtime.notify_connected_superusers(summary) == 1
        assert len(messages) == 1

    def test_account_whose_msg_raises_is_skipped(self) -> None:
        def _boom(text: str) -> None:
            raise RuntimeError("boom")

        bad = SimpleNamespace(
            is_superuser=True, permissions=FakePermissions(set()), msg=_boom
        )
        staff_messages: list[str] = []
        sessions = [
            SimpleNamespace(account=bad),
            _session(True, set(), staff_messages),
        ]
        summary = runtime.ValidationSummary(content_path="x", entity_count=0)
        with mock.patch.object(runtime, "_connected_sessions", return_value=sessions):
            assert runtime.notify_connected_superusers(summary) == 1
        assert len(staff_messages) == 1

    def test_validate_on_start_notifies_when_findings_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "c.yaml").write_text(
                "schema_version: 1\nentities:\n  - id: a\n"
                '    kind: object\n    key: x\n    location: "@nope"\n',
                encoding="utf-8",
            )
            with (
                self.settings(MUDIFICATION_CONTENT_PATH=directory),
                mock.patch.object(runtime, "notify_connected_superusers") as notify,
            ):
                runtime.validate_on_start()
        assert notify.call_count == 1

    def test_validate_on_start_is_silent_when_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "c.yaml").write_text(
                "schema_version: 1\nentities:\n  - id: a\n    kind: room\n    key: a\n",
                encoding="utf-8",
            )
            with (
                self.settings(MUDIFICATION_CONTENT_PATH=directory),
                mock.patch.object(runtime, "notify_connected_superusers") as notify,
                mock.patch.object(runtime, "register_prototypes", return_value=1),
            ):
                runtime.validate_on_start()
        assert notify.call_count == 0
