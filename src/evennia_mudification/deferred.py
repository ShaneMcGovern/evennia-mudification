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


def _deferral_safe() -> bool:
    """Whether a worker thread may touch the database.

    Evennia's `run_async` warns that sqlite has no support for concurrent
    access from threads, and the stock install is sqlite.
    """
    from django.db import connection

    vendor: str = connection.vendor
    return vendor != "sqlite"


def _with_closed_connections(to_execute: Callable[[], Any]) -> Callable[[], Any]:
    """Give the worker's ORM use its own connection lifecycle."""

    def _work() -> Any:
        from django.db import close_old_connections

        close_old_connections()
        try:
            return to_execute()
        finally:
            close_old_connections()

    return _work


def run_deferred(
    to_execute: Callable[[], Any],
    *,
    at_return: Callable[[Any], None] | None = None,
    at_err: Callable[[Exception], None] | None = None,
) -> bool:
    """Run `to_execute` in a worker thread when a reactor is running.

    Returns True when deferred (callbacks fire later, on the reactor thread),
    False when inline. Deferral is skipped when the database cannot take
    worker-thread access.
    """
    if _reactor_running() and _deferral_safe():
        from evennia.utils.utils import run_async

        run_async(
            _with_closed_connections(to_execute), at_return=at_return, at_err=at_err
        )
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
