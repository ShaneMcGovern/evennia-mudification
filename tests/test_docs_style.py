"""Pin the plain style rule across the public documents."""

from pathlib import Path

# RUF001 reads the en dash as an ambiguous character; here it is the test data.
BANNED = ("—", "–", "…", "§", "→")  # noqa: RUF001

DOCUMENTS = (
    "README.md",
    "docs/authoring-guide.md",
    "CONTRIBUTING.md",
)

# The shipped documents must never pin a release version, because a release
# only rewrites pyproject.toml and uv.lock.
SHIPPED = ("README.md", "docs/authoring-guide.md", "CONTRIBUTING.md")

ROOT = Path(__file__).parent.parent


def test_shipped_documents_do_not_hardcode_the_release_version() -> None:
    import tomllib

    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    for name in SHIPPED:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert version not in text, f"{name} hardcodes version {version}"


def test_no_banned_characters() -> None:
    for name in DOCUMENTS:
        text = (ROOT / name).read_text(encoding="utf-8")
        for character in BANNED:
            assert character not in text, f"{name} contains {character!r}"
