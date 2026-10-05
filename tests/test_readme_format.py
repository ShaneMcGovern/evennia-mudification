"""Pin the README to the contrib README shape Evennia parses."""

import re
from pathlib import Path

README = Path(__file__).parent.parent / "README.md"

CREDIT = re.compile(r"^Contribution by .+, \d{4}$")


def _lines() -> list[str]:
    return README.read_text(encoding="utf-8").splitlines()


def test_title_is_first_line() -> None:
    first = _lines()[0]
    assert first.startswith("# ")
    assert first.count("#") == 1


def test_credit_line_second_nonblank_line() -> None:
    nonblank = [line for line in _lines() if line.strip()]
    assert CREDIT.match(nonblank[1]), nonblank[1]


def test_summary_paragraph_is_present() -> None:
    lines = _lines()
    nonblank = [index for index, line in enumerate(lines) if line.strip()]
    assert len(nonblank) > 2, "no line after the credit line"
    paragraph: list[str] = []
    for line in lines[nonblank[2] :]:
        if not line.strip():
            break
        paragraph.append(line)
    assert paragraph, "the credit line is not followed by a paragraph"
    assert not paragraph[0].startswith(("#", "[", "!", "|", ">")), (
        f"the paragraph after the credit line is markup: {paragraph[0]!r}"
    )
    assert len(" ".join(paragraph)) > 80  # the parsed summary is a real paragraph


def test_required_sections_in_order() -> None:
    text = README.read_text(encoding="utf-8")
    positions = [
        text.index("## Installation"),
        text.index("## Usage"),
        text.index("## Examples"),
    ]
    assert positions == sorted(positions)
