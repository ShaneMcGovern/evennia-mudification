"""Reading content bundles from a source location."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SourceDocument:
    """One raw bundle file read from a content source."""

    path: Path
    text: str


class ContentSource(Protocol):
    """A location content bundles can be read from."""

    def documents(self) -> list[SourceDocument]:
        """Return every bundle, sorted by path for deterministic output."""
        ...


class LocalDirectorySource:
    """Read `*.yaml` and `*.yml` bundles from a local directory tree."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def documents(self) -> list[SourceDocument]:
        paths = sorted(
            [
                *self.root.glob("**/*.yaml"),
                *self.root.glob("**/*.yml"),
            ]
        )
        return [
            SourceDocument(path=path, text=path.read_text(encoding="utf-8"))
            for path in paths
            if path.is_file()
        ]
