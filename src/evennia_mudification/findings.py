"""Validation findings shared by the compiler, validator and CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Finding:
    """One problem found in content, anchored to its source file."""

    severity: Severity
    code: str
    message: str
    source: str
    entity_id: str | None = None

    def render(self) -> str:
        anchor = f"{self.source}:{self.entity_id}" if self.entity_id else self.source
        return f"{anchor}: [{self.severity}] {self.code}: {self.message}"
