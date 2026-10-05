"""Pin the plain style rule across the public documents."""

from pathlib import Path

# RUF001 reads the en dash as an ambiguous character; here it is the test data.
BANNED = ("—", "–", "…", "§", "→")  # noqa: RUF001

DOCUMENTS = (
    "README.md",
    "docs/authoring-guide.md",
)

ROOT = Path(__file__).parent.parent


def test_no_banned_characters() -> None:
    for name in DOCUMENTS:
        text = (ROOT / name).read_text(encoding="utf-8")
        for character in BANNED:
            assert character not in text, f"{name} contains {character!r}"
