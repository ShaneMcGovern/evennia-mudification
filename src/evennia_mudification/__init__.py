"""Mudification: YAML-defined world content for Evennia."""

from typing import Any

__all__ = ["validate_on_start"]


def __getattr__(name: str) -> Any:
    """Import Evennia-dependent names on first use.

    A module-level import would make every `import evennia_mudification` -
    including the standalone CLI - require a configured Django/Evennia, which
    the CLI deliberately avoids until its semantic checks need it.
    """
    if name == "validate_on_start":
        from evennia_mudification.runtime import validate_on_start

        return validate_on_start
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
