"""Reading content bundles from a source location."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class SourceReadError(Exception):
    """A bundle file could not be read; `path` anchors the finding."""

    def __init__(self, path: Path, cause: Exception) -> None:
        super().__init__(f"{path}: {cause}")
        self.path = path


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
        documents = []
        for path in paths:
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as err:
                raise SourceReadError(path, err) from err
            documents.append(SourceDocument(path=path, text=text))
        return documents
