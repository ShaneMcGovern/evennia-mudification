"""Check the worked examples in the shipped documents against the engine.

The bundles, counts and transcripts in the README and the author guide are
written by hand; these tests compile every bundle and cross-check what the
prose claims, so a fixture or output change cannot leave them silently wrong.
"""

import re
from pathlib import Path

import pytest

from evennia_mudification.compile import compile_documents
from evennia_mudification.findings import Finding
from evennia_mudification.source import SourceDocument
from evennia_mudification.validate import validate_index

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ("README.md", "docs/authoring-guide.md")

YAML_BLOCK = re.compile(r"```yaml\n(.*?)```", re.S)
TEXT_BLOCK = re.compile(r"```text\n(.*?)```", re.S)
# The CLI summary form, and the in-game form that only counts entities.
COUNT_CLAIM = re.compile(r"(\d+) entities, (\d+) errors, (\d+) warnings")
VALID_CLAIM = re.compile(r"(\d+) entities valid\.")
PAYLOAD_LINE = re.compile(
    r"^(?:create|retire|destroy|update) ([A-Za-z0-9_-]+(?:#\d+|:reverse)?)\b", re.M
)


def _compile(body: str) -> tuple[int, list[Finding]]:
    index = compile_documents([SourceDocument(path=Path("example.yaml"), text=body)])
    findings = index.findings + validate_index(index, check_evennia=True)
    return len(index.entities), findings


def _assert_clean(body: str, origin: str) -> None:
    _, findings = _compile(body)
    assert findings == [], f"{origin} does not validate: {findings}"


@pytest.mark.parametrize("name", DOCUMENTS)
def test_every_bundle_validates_clean(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    blocks = list(YAML_BLOCK.finditer(text))
    assert blocks, f"{name} has no bundles to check"
    for match in blocks:
        _assert_clean(match.group(1), f"{name} at offset {match.start()}")


@pytest.mark.parametrize("name", DOCUMENTS)
def test_count_claims_match_the_bundles(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    checked = 0
    for match in YAML_BLOCK.finditer(text):
        window = text[match.end() : match.end() + 400]
        claim = COUNT_CLAIM.search(window)
        valid = VALID_CLAIM.search(window)
        if claim is None and valid is None:
            continue
        entities, findings = _compile(match.group(1))
        if claim is not None:
            errors = [finding for finding in findings if finding.severity == "error"]
            warnings = [
                finding for finding in findings if finding.severity == "warning"
            ]
            assert (entities, len(errors), len(warnings)) == tuple(
                int(group) for group in claim.groups()
            ), f"{name} at offset {match.start()}"
        elif valid is not None:
            assert entities == int(valid.group(1)), f"{name} at offset {match.start()}"
        checked += 1
    assert checked >= 1, f"{name} has no count claims to check"


@pytest.mark.parametrize("name", DOCUMENTS)
def test_transcripts_only_name_declared_entities(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    declared = [
        set(re.findall(r"^\s*- id: (\S+)", match.group(1), re.M))
        for match in YAML_BLOCK.finditer(text)
    ]
    checked = 0
    for match in TEXT_BLOCK.finditer(text):
        preceding = [
            ids
            for block, ids in zip(YAML_BLOCK.finditer(text), declared, strict=True)
            if block.end() < match.start()
        ]
        if not preceding:
            continue
        known = preceding[-1]
        for entity_id in PAYLOAD_LINE.findall(match.group(1)):
            base = entity_id.split("#")[0].split(":")[0]
            assert base in known, (
                f"{name} transcript names '{entity_id}', not declared in the "
                f"preceding bundle"
            )
            checked += 1
    assert checked >= 5, f"{name} has only {checked} transcript lines to check"
