"""Deferral under a real Twisted reactor.

Every other test mocks the reactor, which hides the real thread and callback
behavior. A reactor can start only once per process, so the whole path runs in
one test.
"""

from pathlib import Path
from typing import Any, cast
from unittest import mock

from evennia.utils import create
from evennia.utils.test_resources import BaseEvenniaTestCase
from twisted.internet import reactor as _reactor

from evennia_mudification import deferred, runtime
from evennia_mudification.commands import CmdMudification
from evennia_mudification.identity import find_entity_object

# Twisted installs the reactor by replacing the module at import time, which
# its type stubs cannot express.
reactor = cast("Any", _reactor)

CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "basic"

# A reactor whose scenario wedges would hang the suite; stop it anyway.
HANG_GUARD_SECONDS = 30


class TestRunDeferredUnderARealReactor(BaseEvenniaTestCase):
    def test_real_reactor_paths(self) -> None:
        if deferred._deferral_safe():
            self.skipTest("expected Evennia's stock sqlite settings")

        results: dict[str, Any] = {}

        def scenario() -> None:
            results["reactor_running"] = deferred._reactor_running()

            # On sqlite the reactor's own thread runs the work.
            calls: list[str] = []
            results["inline_return"] = deferred.run_deferred(
                lambda: "inline", at_return=calls.append
            )
            results["inline_calls"] = calls

            # The command path end to end, still inline.
            output: list[str] = []
            cmd = CmdMudification()
            cmd.caller = create.create_object(
                "evennia.objects.objects.DefaultCharacter", key="Caller"
            )
            cmd.args = "apply confirm"
            cmd.msg = lambda text=None, **kwargs: output.append(str(text))
            with self.settings(MUDIFICATION_CONTENT_PATH=str(CORPUS)):
                cmd.func()
            results["command_output"] = "\n".join(output)
            results["square_created"] = find_entity_object("square") is not None
            results["flag_after_inline"] = runtime.RUN_IN_FLIGHT

            # Forced deferral: the work crosses a real thread and its callback
            # returns to the reactor.
            with mock.patch.object(deferred, "_deferral_safe", return_value=True):

                def at_return(value: str) -> None:
                    results["threaded_value"] = value
                    reactor.stop()

                def at_err(err: Any) -> None:
                    results["threaded_error"] = err
                    reactor.stop()

                results["deferred_return"] = deferred.run_deferred(
                    lambda: "threaded", at_return=at_return, at_err=at_err
                )

        reactor.callWhenRunning(scenario)
        reactor.callLater(HANG_GUARD_SECONDS, reactor.stop)
        reactor.run()

        assert results["reactor_running"] is True
        assert results["inline_return"] is False
        assert results["inline_calls"] == ["inline"]
        assert "off-thread" not in results["command_output"]
        assert "create square: ok" in results["command_output"]
        assert results["square_created"] is True
        assert results["flag_after_inline"] is False
        assert "threaded_error" not in results
        assert results["deferred_return"] is True
        assert results["threaded_value"] == "threaded"
