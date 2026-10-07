"""Tests for the deferral helper."""

from typing import Any
from unittest.mock import patch

from evennia.utils.test_resources import BaseEvenniaTestCase

from evennia_mudification import deferred


class TestRunDeferred(BaseEvenniaTestCase):
    def test_runs_inline_without_reactor(self) -> None:
        calls: list[str] = []

        def work() -> str:
            calls.append("ran")
            return "value"

        deferred_result = deferred.run_deferred(work, at_return=calls.append)
        assert deferred_result is False
        assert calls == ["ran", "value"]

    def test_errors_propagate_to_at_err(self) -> None:
        seen: list[Exception] = []

        def boom() -> None:
            raise RuntimeError("boom")

        assert deferred.run_deferred(boom, at_err=seen.append) is False
        assert isinstance(seen[0], RuntimeError)

    def test_defers_when_reactor_running(self) -> None:
        calls: list[tuple[Any, ...]] = []
        with (
            patch.object(deferred, "_reactor_running", return_value=True),
            patch.object(deferred, "_deferral_safe", return_value=True),
            patch(
                "evennia.utils.utils.run_async",
                side_effect=lambda *a, **kw: calls.append((a, kw)),
            ),
        ):
            assert deferred.run_deferred(lambda: "x", at_return=print) is True
        assert calls and calls[0][1].get("at_return") is print

    def test_inline_error_raises_without_errback(self) -> None:
        def boom() -> None:
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            deferred.run_deferred(boom)

    def test_reactor_running_is_false_in_tests(self) -> None:
        # No reactor runs under pytest; reporting that honestly selects the
        # inline path in every other test here.
        assert deferred._reactor_running() is False

    def test_deferral_is_unsafe_on_sqlite(self) -> None:
        # The suite runs on Evennia's stock sqlite settings; the check must
        # see that, because sqlite cannot take Evennia's worker-thread access.
        assert deferred._deferral_safe() is False

    def test_sqlite_skips_deferral_even_with_reactor(self) -> None:
        calls: list[str] = []
        with (
            patch.object(deferred, "_reactor_running", return_value=True),
            patch("evennia.utils.utils.run_async") as run_async_mock,
        ):
            deferred_result = deferred.run_deferred(
                lambda: "value", at_return=calls.append
            )
        assert deferred_result is False
        assert calls == ["value"]
        assert run_async_mock.call_count == 0

    def test_deferred_run_closes_connections_around_the_work(self) -> None:
        executed: list[str] = []
        with (
            patch.object(deferred, "_reactor_running", return_value=True),
            patch.object(deferred, "_deferral_safe", return_value=True),
            patch("django.db.close_old_connections") as close_mock,
            patch(
                "evennia.utils.utils.run_async",
                side_effect=lambda work, **kwargs: executed.append(work()),
            ),
        ):
            assert deferred.run_deferred(lambda: "x", at_return=print) is True
        assert executed == ["x"]
        assert close_mock.call_count == 2
