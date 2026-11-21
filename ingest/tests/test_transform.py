import json
from dataclasses import fields
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from cardwise_ingest.load import TABLES
from cardwise_ingest.scryfall import BulkType
from cardwise_ingest.transform import (
    IMAGE_SIZES,
    CardRow,
    CardTagRow,
    Corpus,
    FaceRow,
    RulingRow,
    TagEdge,
    TagRow,
    build_corpus,
)

type Lines = dict[BulkType, list[str]]


def build(tmp_path: Path, lines: Lines) -> Corpus:
    paths = {}
    for bulk_type, content in lines.items():
        paths[bulk_type] = tmp_path / f"{bulk_type}.jsonl"
        paths[bulk_type].write_text("".join(content), encoding="utf-8")
    return build_corpus(paths["oracle_cards"], paths["rulings"], paths["oracle_tags"])


def card(corpus: Corpus, name: str) -> CardRow:
    return next(c for c in corpus.cards if c.name == name)


def faces(corpus: Corpus, name: str) -> list[FaceRow]:
    oracle_id = card(corpus, name).oracle_id
    return sorted((f for f in corpus.faces if f.oracle_id == oracle_id), key=lambda f: f.face_index)


def raw_cards(lines: Lines) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in map(json.loads, lines["oracle_cards"])}


@pytest.fixture
def corpus(tmp_path: Path, bulk_lines: Lines) -> Corpus:
    return build(tmp_path, bulk_lines)


def test_fixtures_load_cleanly(corpus: Corpus, bulk_lines: Lines) -> None:
    assert corpus.quarantine == []
    assert corpus.errors == []
    assert len(corpus.cards) == len(bulk_lines["oracle_cards"])
    assert len(corpus.rulings) == len(bulk_lines["rulings"])
    assert len(corpus.tags) == len(bulk_lines["oracle_tags"])
    assert corpus.card_tags
    assert corpus.tag_edges


def test_row_fields_match_loader_columns() -> None:
    rows = {
        "cards": CardRow,
        "card_faces": FaceRow,
        "rulings": RulingRow,
        "tags": TagRow,
        "tag_parents": TagEdge,
        "card_tags": CardTagRow,
    }
    for table, row in rows.items():
        assert [f.name for f in fields(row)] == TABLES[table], table


def test_modal_dfc_takes_cost_text_and_image_from_faces(corpus: Corpus, bulk_lines: Lines) -> None:
    name = "Agadeem's Awakening // Agadeem, the Undercrypt"
    row = card(corpus, name)
    raw = raw_cards(bulk_lines)[name]
    assert row.mana_cost == "{X}{B}{B}{B}"
    assert row.mana_value == Decimal(3)
    assert row.colors == ("B",)
    assert row.oracle_text == "\n\n".join(f["oracle_text"] for f in raw["card_faces"])
    assert row.image_uris is not None
    assert row.image_uris["normal"] == raw["card_faces"][0]["image_uris"]["normal"]
    front, back = faces(corpus, name)
    assert (front.name, back.name) == ("Agadeem's Awakening", "Agadeem, the Undercrypt")
    assert back.mana_cost is None
    assert back.type_line == "Land"


def test_transform_card_keeps_face_stats(corpus: Corpus) -> None:
    row = card(corpus, "Delver of Secrets // Insectile Aberration")
    assert row.mana_cost == "{U}"
    assert row.colors == ("U",)
    front, back = faces(corpus, "Delver of Secrets // Insectile Aberration")
    assert (front.power, front.toughness, back.power, back.toughness) == ("1", "1", "3", "2")
    assert back.oracle_text == "Flying"


def test_battle_face_has_defense(corpus: Corpus) -> None:
    front, back = faces(corpus, "Invasion of Zendikar // Awakened Skyclave")
    assert front.defense == "3"
    assert back.defense is None


def test_split_card_keeps_combined_cost_and_orders_colors(corpus: Corpus) -> None:
    row = card(corpus, "Fire // Ice")
    assert row.mana_cost == "{1}{R} // {1}{U}"
    assert row.colors == ("U", "R")
    assert row.oracle_text is not None
    assert row.oracle_text.startswith("Fire deals 2 damage")
    assert "Tap target permanent." in row.oracle_text


def test_adventure_text_is_searchable(corpus: Corpus) -> None:
    row = card(corpus, "Bonecrusher Giant // Stomp")
    assert "Damage can't be prevented this turn." in row.search_text
    assert row.image_uris is not None
    assert [f.image_uris for f in faces(corpus, "Bonecrusher Giant // Stomp")] == [None, None]


def test_flip_card_has_faces_but_one_image(corpus: Corpus) -> None:
    row = card(corpus, "Akki Lavarunner // Tok-Tok, Volcano Born")
    assert row.image_uris is not None
    assert len(faces(corpus, row.name)) == 2


def test_meld_card_is_single_faced(corpus: Corpus) -> None:
    row = card(corpus, "Bruna, the Fading Light")
    assert faces(corpus, row.name) == []
    assert row.oracle_text


def test_extreme_mana_values(corpus: Corpus) -> None:
    assert card(corpus, "Gleemax").mana_value == Decimal(1_000_000)
    assert card(corpus, "Little Girl").mana_value == Decimal("0.5")


def test_colorless_commander_has_empty_identity(corpus: Corpus) -> None:
    row = card(corpus, "Kozilek, Butcher of Truth")
    assert row.color_identity == ()
    assert row.legalities["commander"] == "legal"


def test_colors_outside_identity_are_kept(corpus: Corpus) -> None:
    """Fallaji Wayfarer is every color but has a green identity; that is real data."""
    row = card(corpus, "Fallaji Wayfarer")
    assert row.colors == ("W", "U", "B", "R", "G")
    assert row.color_identity == ("G",)


def test_token_is_not_a_game_card(corpus: Corpus) -> None:
    row = card(corpus, "Goblin")
    assert not row.is_game_card
    assert row.mana_cost is None
    assert card(corpus, "Sol Ring").is_game_card


def test_payload_drops_volatile_and_duplicated_fields(corpus: Corpus) -> None:
    row = card(corpus, "Llanowar Elves")
    for dropped in ("prices", "purchase_uris", "legalities", "image_uris", "oracle_text"):
        assert dropped not in row.payload
    for printing_only in ("set_id", "frame", "foil", "collector_number", "image_status"):
        assert printing_only not in row.payload
    assert row.payload["power"] == "1"
    assert row.payload["rarity"]
    assert row.payload["set_name"]
    assert row.image_uris is not None
    assert set(row.image_uris) <= set(IMAGE_SIZES)


def test_edges_come_from_both_parent_and_child_lists(corpus: Corpus, bulk_lines: Lines) -> None:
    tags = [json.loads(line) for line in bulk_lines["oracle_tags"]]
    expected = {(UUID(t["id"]), UUID(p)) for t in tags for p in t["parent_ids"]}
    expected |= {(UUID(c), UUID(t["id"])) for t in tags for c in t["child_ids"]}
    assert {(e.tag_id, e.parent_id) for e in corpus.tag_edges} == expected


def test_bad_lines_are_quarantined(tmp_path: Path, bulk_lines: Lines) -> None:
    sol_ring = raw_cards(bulk_lines)["Sol Ring"]
    no_id = {k: v for k, v in sol_ring.items() if k != "oracle_id"}
    phyrexian = dict(sol_ring, oracle_id="00000000-0000-0000-0000-000000000001", colors=["P"])
    lines = dict(bulk_lines)
    lines["oracle_cards"] = [
        *bulk_lines["oracle_cards"],
        "{not json\n",
        json.dumps(no_id) + "\n",
        json.dumps(phyrexian) + "\n",
    ]
    corpus = build(tmp_path, lines)
    assert [q.source for q in corpus.quarantine] == ["cards"] * 3
    assert corpus.quarantine[0].record_key == f"line {len(bulk_lines['oracle_cards']) + 1}"
    assert "oracle_id" in corpus.quarantine[1].reason
    assert corpus.errors == []
    assert len(corpus.cards) == len(bulk_lines["oracle_cards"])


def test_duplicate_oracle_id_is_an_error(tmp_path: Path, bulk_lines: Lines) -> None:
    lines = dict(bulk_lines)
    lines["oracle_cards"] = [*bulk_lines["oracle_cards"], bulk_lines["oracle_cards"][0]]
    corpus = build(tmp_path, lines)
    assert len(corpus.errors) == 1
    assert "duplicate oracle_id" in corpus.errors[0]


def test_records_for_unknown_cards_are_quarantined(tmp_path: Path, bulk_lines: Lines) -> None:
    unknown = "00000000-0000-0000-0000-00000000beef"
    ruling = dict(json.loads(bulk_lines["rulings"][0]), oracle_id=unknown)
    tag = json.loads(bulk_lines["oracle_tags"][0])
    tag["taggings"] = [*tag["taggings"], {"oracle_id": unknown, "weight": "median"}]
    lines = dict(bulk_lines)
    lines["rulings"] = [*bulk_lines["rulings"], json.dumps(ruling) + "\n"]
    lines["oracle_tags"] = [json.dumps(tag) + "\n", *bulk_lines["oracle_tags"][1:]]
    corpus = build(tmp_path, lines)
    assert {(q.source, q.record_key) for q in corpus.quarantine} == {
        ("rulings", unknown),
        ("tags", f"{tag['slug']}:{unknown}"),
    }


def test_invalid_tag_is_quarantined_with_its_taggings_counted(
    tmp_path: Path, bulk_lines: Lines
) -> None:
    tag = json.loads(bulk_lines["oracle_tags"][0])
    tag["slug"] = "Not A Slug"
    lines = dict(bulk_lines)
    lines["oracle_tags"] = [json.dumps(tag) + "\n", *bulk_lines["oracle_tags"][1:]]
    clean = build(tmp_path, bulk_lines)
    corpus = build(tmp_path, lines)
    assert corpus.quarantined("tags") >= 1
    assert corpus.seen["tags"] == clean.seen["tags"]
    assert "taggings" not in corpus.quarantine[0].payload


def test_tag_cycle_is_an_error(tmp_path: Path) -> None:
    a, b = "00000000-0000-0000-0000-00000000000a", "00000000-0000-0000-0000-00000000000b"

    def tag(tag_id: str, slug: str, parent: str) -> str:
        return json.dumps(
            {"id": tag_id, "slug": slug, "label": slug, "type": "oracle", "parent_ids": [parent]}
        )

    corpus = build(
        tmp_path,
        {
            "oracle_cards": [],
            "rulings": [],
            "oracle_tags": [tag(a, "alpha", b) + "\n", tag(b, "beta", a) + "\n"],
        },
    )
    assert len(corpus.errors) == 1
    assert corpus.errors[0].startswith("tag hierarchy has a cycle")
