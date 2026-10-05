"""Run work off the reactor thread when possible, inline otherwise."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _reactor_running() -> bool:
    try:
        from twisted.internet import reactor
    except ImportError:  # pragma: no cover - twisted ships with Evennia
        return False
    return bool(getattr(reactor, "running", False))


def run_deferred(
    to_execute: Callable[[], Any],
    *,
    at_return: Callable[[Any], None] | None = None,
    at_err: Callable[[Exception], None] | None = None,
) -> bool:
    """Run `to_execute` in a worker thread when a reactor is running.

    Returns True when deferred (callbacks fire later, on the reactor thread),
    False when inline. Caveat: heavy database work from a second thread is
    poor on sqlite; large worlds should run postgres.
    """
    if _reactor_running():
        from evennia.utils.utils import run_async

        run_async(to_execute, at_return=at_return, at_err=at_err)
        return True
    try:
        result = to_execute()
    except Exception as err:
        if at_err is None:
            raise
        at_err(err)
    else:
        if at_return is not None:
            at_return(result)
    return False
