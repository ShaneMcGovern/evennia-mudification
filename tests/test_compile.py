"""Tests for the compiler."""

from pathlib import Path

from evennia_mudification.compile import compile_documents
from evennia_mudification.models import ExitEntity, ObjectEntity, RoomEntity
from evennia_mudification.source import LocalDirectorySource

CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "basic"


def test_compiles_valid_corpus() -> None:
    index = compile_documents(LocalDirectorySource(CORPUS).documents())
    assert set(index.entities) == {"square", "inn", "square-inn", "signpost"}
    assert index.findings == []
    assert index.entity_sources["square"].endswith("village.yaml")


def test_duplicate_id_reports_both_files(tmp_path: Path) -> None:
    one = tmp_path / "one.yaml"
    one.write_text(
        "schema_version: 1\nentities:\n  - id: dup\n    kind: room\n    key: one\n"
    )
    two = tmp_path / "two.yaml"
    two.write_text(
        "schema_version: 1\nentities:\n  - id: dup\n    kind: room\n    key: two\n"
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    codes = [finding.code for finding in index.findings]
    assert "duplicate-id" in codes
    duplicate = next(f for f in index.findings if f.code == "duplicate-id")
    assert "one.yaml" in duplicate.message
    assert "two.yaml" in duplicate.source


def test_invalid_yaml_reports_parse_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("entities: [unclosed\n")
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert [finding.code for finding in index.findings] == ["yaml-parse"]


def test_schema_error_reports_field_location(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "schema_version: 1\nentities:\n  - id: room\n"
        "    kind: room\n    key: x\n    locaton: y\n"
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    finding = index.findings[0]
    assert finding.code == "schema"
    assert "locaton" in finding.message


def test_empty_file_is_reported(tmp_path: Path) -> None:
    (tmp_path / "empty.yaml").write_text("")
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert index.entities == {}
    assert [finding.code for finding in index.findings] == ["empty-bundle"]
    assert "empty.yaml" in index.findings[0].source


def test_contents_are_flattened_with_location(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: hall\n    kind: room\n    key: hall\n"
        "    contents:\n"
        "      - id: chest\n        kind: object\n        key: chest\n"
        "        contents:\n"
        "          - id: coin\n            kind: object\n            key: coin\n"
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    hall = index.entities["hall"]
    chest = index.entities["chest"]
    coin = index.entities["coin"]
    assert isinstance(hall, RoomEntity)
    assert isinstance(chest, ObjectEntity)
    assert isinstance(coin, ObjectEntity)
    assert index.findings == []
    assert chest.location == "@hall"
    assert coin.location == "@chest"
    assert hall.contents == []
    assert chest.contents == []


def test_nested_child_with_location_is_error(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: hall\n    kind: room\n    key: hall\n"
        "    contents:\n"
        "      - id: chest\n        kind: object\n        key: chest\n"
        '        location: "@hall"\n'
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert [finding.code for finding in index.findings] == ["nested-location"]
    assert "chest" not in index.entities


def test_nested_non_object_child_is_a_schema_error(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: hall\n    kind: room\n    key: hall\n"
        "    contents:\n"
        "      - id: inner\n        kind: room\n        key: inner\n"
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert [finding.code for finding in index.findings] == ["schema"]


def test_count_expands_to_instances(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: rats\n    kind: object\n    key: a rat\n    count: 3\n"
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert "rats" not in index.entities
    assert set(index.entities) == {"rats#1", "rats#2", "rats#3"}
    rat = index.entities["rats#2"]
    assert isinstance(rat, ObjectEntity)
    assert rat.count is None


def test_count_with_contents_is_error(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: rats\n    kind: object\n    key: a rat\n    count: 2\n"
        "    contents:\n"
        "      - id: flea\n        kind: object\n        key: a flea\n"
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert [finding.code for finding in index.findings] == ["count-with-contents"]


def test_reverse_exit_is_synthesized(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: hall\n    kind: room\n    key: The Great Hall\n"
        "  - id: cellar\n    kind: room\n    key: the cellar\n"
        "  - id: stairs\n    kind: exit\n    key: down\n"
        '    location: "@hall"\n    destination: "@cellar"\n    reverse: true\n'
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert index.findings == []
    reverse = index.entities["stairs:reverse"]
    assert isinstance(reverse, ExitEntity)
    assert reverse.location == "@cellar"
    assert reverse.destination == "@hall"
    assert reverse.key == "The Great Hall"


def test_reverse_override_key_and_aliases(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: hall\n    kind: room\n    key: The Great Hall\n"
        "  - id: cellar\n    kind: room\n    key: the cellar\n"
        "  - id: stairs\n    kind: exit\n    key: down\n"
        '    location: "@hall"\n    destination: "@cellar"\n'
        "    reverse: {key: climb up, aliases: [up]}\n"
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    reverse = index.entities["stairs:reverse"]
    assert reverse.key == "climb up"
    assert reverse.aliases == ["up"]


def test_nested_duplicate_id_is_error(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: chest\n    kind: object\n    key: chest\n"
        "  - id: hall\n    kind: room\n    key: hall\n"
        "    contents:\n"
        "      - id: chest\n        kind: object\n        key: chest\n"
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert [finding.code for finding in index.findings] == ["duplicate-id"]
    # The top-level declaration wins; the nested one never overwrites it.
    assert index.entities["chest"].kind == "object"


def test_duplicate_nested_child_names_discarded_descendants(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: chest\n    kind: object\n    key: chest\n"
        "  - id: hall\n    kind: room\n    key: hall\n"
        "    contents:\n"
        "      - id: chest\n        kind: object\n        key: chest\n"
        "        contents:\n"
        "          - id: coin\n            kind: object\n            key: coin\n"
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    finding = index.findings[0]
    assert finding.code == "duplicate-id"
    assert "coin" in finding.message


def test_deep_nesting_reports_yaml_parse_instead_of_raising(tmp_path: Path) -> None:
    depth = 400
    lines = ["schema_version: 1", "entities:"]
    for level in range(depth):
        item_pad = " " * (2 + 4 * level)
        key_pad = " " * (4 + 4 * level)
        kind = "room" if level == 0 else "object"
        lines.append(f"{item_pad}- id: e{level}")
        lines.append(f"{key_pad}kind: {kind}")
        lines.append(f"{key_pad}key: e{level}")
        if level + 1 < depth:
            lines.append(f"{key_pad}contents:")
    (tmp_path / "deep.yaml").write_text("\n".join(lines) + "\n")
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert [finding.code for finding in index.findings] == ["yaml-parse"]


def test_nested_count_with_contents_is_error(tmp_path: Path) -> None:
    (tmp_path / "c.yaml").write_text(
        "schema_version: 1\nentities:\n"
        "  - id: hall\n    kind: room\n    key: hall\n"
        "    contents:\n"
        "      - id: rats\n        kind: object\n        key: a rat\n"
        "        count: 2\n"
        "        contents:\n"
        "          - id: flea\n            kind: object\n            key: a flea\n"
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert [finding.code for finding in index.findings] == ["count-with-contents"]
    rats = index.entities["rats"]
    assert isinstance(rats, ObjectEntity)
    assert rats.count == 2
    assert rats.location == "@hall"
    assert "rats#1" not in index.entities
    assert "flea" not in index.entities
    # No location ref dangles after expansion.
    for entity in index.entities.values():
        if isinstance(entity, ObjectEntity) and entity.location is not None:
            assert entity.location.removeprefix("@") in index.entities


def test_schema_error_omits_the_union_tag(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text(
        "schema_version: 1\nentities:\n  - id: room\n"
        "    kind: room\n    key: x\n    licks: y\n"
    )
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert index.findings[0].message.startswith("entities.0.licks:")


def test_bundle_level_error_has_no_empty_anchor(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text("schema_version: 2\nentities: []\n")
    index = compile_documents(LocalDirectorySource(tmp_path).documents())
    assert not index.findings[0].message.startswith(":")
