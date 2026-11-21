"""Turn the bulk files into corpus rows.

Each line is parsed on its own. A line that fails goes to quarantine with the reason and the
run continues; `validate` decides whether there were too many. Problems that make the whole
snapshot untrustworthy (duplicate keys, tag cycles) are recorded in `Corpus.errors`.
"""

import gzip
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError

from cardwise_core.cards import NON_GAME_LAYOUTS, Color
from cardwise_ingest.scryfall import OracleTag, ScryfallCard, ScryfallFace, ScryfallRuling, Tagging

Source = Literal["cards", "tags", "rulings"]

IMAGE_SIZES = ("small", "normal", "large", "art_crop")
"""Scryfall serves a dozen image variants; these are the ones the UI uses."""

PAYLOAD_DROP = frozenset(
    {
        # Stored as columns.
        "object", "id", "oracle_id", "name", "layout", "mana_cost", "cmc", "type_line",
        "oracle_text", "colors", "color_identity", "keywords", "legalities", "image_uris",
        "scryfall_uri", "edhrec_rank", "released_at",
        # Prices, store links and API links: large, volatile and not card facts.
        "prices", "purchase_uris", "related_uris", "uri", "rulings_uri", "prints_search_uri",
        "set_uri", "set_search_uri", "scryfall_set_uri",
        # Ids of other systems and print-specific art ids.
        "multiverse_ids", "mtgo_id", "mtgo_foil_id", "tcgplayer_id", "tcgplayer_etched_id",
        "cardmarket_id", "arena_id", "resource_id", "card_back_id", "artist_ids",
        "illustration_id", "preview",
        # Facts about the one printing Scryfall picked, not about the card. Set, rarity,
        # artist and flavor text stay so answers can name where a card comes from.
        "set_id", "set_type", "collector_number", "lang", "image_status", "image_updated_at",
        "highres_image", "border_color", "frame", "frame_effects", "security_stamp", "finishes",
        "foil", "nonfoil", "full_art", "textless", "oversized", "promo", "promo_types",
        "booster", "story_spotlight", "variation", "variation_of", "reprint", "digital",
    }
)  # fmt: skip
FACE_PAYLOAD_DROP = frozenset({"object", "image_uris", "artist_id", "illustration_id"})
PART_PAYLOAD_KEEP = frozenset({"id", "component", "name", "type_line"})
QUARANTINE_REASON_LIMIT = 2000

COLOR_ORDER = {c: i for i, c in enumerate(Color)}


@dataclass(frozen=True, slots=True)
class CardRow:
    oracle_id: UUID
    name: str
    layout: str
    is_game_card: bool
    mana_cost: str | None
    mana_value: Decimal
    type_line: str
    oracle_text: str | None
    colors: tuple[str, ...]
    color_identity: tuple[str, ...]
    keywords: tuple[str, ...]
    legalities: dict[str, str]
    image_uris: dict[str, str] | None
    scryfall_uri: str
    edhrec_rank: int | None
    released_at: date
    search_text: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FaceRow:
    oracle_id: UUID
    face_index: int
    name: str
    mana_cost: str | None
    type_line: str | None
    oracle_text: str | None
    image_uris: dict[str, str] | None
    power: str | None
    toughness: str | None
    loyalty: str | None
    defense: str | None


@dataclass(frozen=True, slots=True)
class RulingRow:
    oracle_id: UUID
    source: str
    published_at: date
    comment: str


@dataclass(frozen=True, slots=True)
class TagRow:
    tag_id: UUID
    slug: str
    label: str
    description: str | None
    aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TagEdge:
    tag_id: UUID
    parent_id: UUID


@dataclass(frozen=True, slots=True)
class CardTagRow:
    tag_id: UUID
    oracle_id: UUID
    weight: str
    annotation: str | None


@dataclass(frozen=True, slots=True)
class QuarantineRow:
    source: Source
    record_key: str | None
    reason: str
    payload: Any


@dataclass
class Corpus:
    cards: list[CardRow] = field(default_factory=list)
    faces: list[FaceRow] = field(default_factory=list)
    rulings: list[RulingRow] = field(default_factory=list)
    tags: list[TagRow] = field(default_factory=list)
    tag_edges: list[TagEdge] = field(default_factory=list)
    card_tags: list[CardTagRow] = field(default_factory=list)
    quarantine: list[QuarantineRow] = field(default_factory=list)
    seen: dict[Source, int] = field(default_factory=lambda: {"cards": 0, "tags": 0, "rulings": 0})
    """Records read per source, quarantined ones included. Taggings count under tags."""
    errors: list[str] = field(default_factory=list)

    def quarantined(self, source: Source) -> int:
        return sum(1 for q in self.quarantine if q.source == source)

    def reject(self, source: Source, key: str | None, reason: str, payload: Any) -> None:
        self.quarantine.append(
            QuarantineRow(source, key, reason[:QUARANTINE_REASON_LIMIT], payload)
        )


def read_jsonl(path: Path) -> Iterator[tuple[int, str]]:
    """Yield (line number, line). Reading the whole gzip also checks its CRC."""
    with (
        gzip.open(path, "rt", encoding="utf-8")
        if path.suffix == ".gz"
        else path.open(encoding="utf-8")
    ) as fh:
        for number, line in enumerate(fh, start=1):
            if line.strip():
                yield number, line


def _sorted_colors(colors: set[Color]) -> tuple[str, ...]:
    return tuple(str(c) for c in sorted(colors, key=COLOR_ORDER.__getitem__))


def _images(uris: dict[str, str] | None) -> dict[str, str] | None:
    if not uris:
        return None
    return {k: uris[k] for k in IMAGE_SIZES if k in uris} or None


def _join(parts: list[str], sep: str) -> str | None:
    kept = [p for p in parts if p]
    return sep.join(kept) if kept else None


def _payload(raw: dict[str, Any]) -> dict[str, Any]:
    payload = {k: v for k, v in raw.items() if k not in PAYLOAD_DROP}
    if isinstance(payload.get("card_faces"), list):
        payload["card_faces"] = [
            {k: v for k, v in face.items() if k not in FACE_PAYLOAD_DROP}
            for face in payload["card_faces"]
            if isinstance(face, dict)
        ]
    if isinstance(payload.get("all_parts"), list):
        payload["all_parts"] = [
            {k: v for k, v in part.items() if k in PART_PAYLOAD_KEEP}
            for part in payload["all_parts"]
            if isinstance(part, dict)
        ]
    return payload


def card_rows(card: ScryfallCard, raw: dict[str, Any]) -> tuple[CardRow, list[FaceRow]]:
    faces = card.card_faces
    mana_cost = (
        card.mana_cost
        if card.mana_cost is not None
        else _join([f.mana_cost for f in faces], " // ")
    )
    oracle_text = (
        card.oracle_text
        if card.oracle_text is not None
        else _join([f.oracle_text for f in faces], "\n\n")
    )
    if card.colors is not None:
        colors = _sorted_colors(set(card.colors))
    else:
        colors = _sorted_colors({c for f in faces for c in f.colors or ()})
    image_uris = _images(card.image_uris) or (_images(faces[0].image_uris) if faces else None)
    search_text = "\n".join(
        p for p in (card.name, card.type_line, oracle_text, " ".join(card.keywords)) if p
    )
    row = CardRow(
        oracle_id=card.oracle_id,
        name=card.name,
        layout=card.layout,
        is_game_card=card.layout not in NON_GAME_LAYOUTS,
        mana_cost=mana_cost or None,
        mana_value=Decimal(str(card.cmc)),
        type_line=card.type_line,
        oracle_text=oracle_text,
        colors=colors,
        color_identity=_sorted_colors(set(card.color_identity)),
        keywords=card.keywords,
        legalities=dict(card.legalities),
        image_uris=image_uris,
        scryfall_uri=card.scryfall_uri,
        edhrec_rank=card.edhrec_rank,
        released_at=card.released_at,
        search_text=search_text,
        payload=_payload(raw),
    )
    return row, [_face_row(card.oracle_id, i, f) for i, f in enumerate(faces)]


def _face_row(oracle_id: UUID, index: int, face: ScryfallFace) -> FaceRow:
    return FaceRow(
        oracle_id=oracle_id,
        face_index=index,
        name=face.name,
        mana_cost=face.mana_cost or None,
        type_line=face.type_line,
        oracle_text=face.oracle_text or None,
        image_uris=_images(face.image_uris),
        power=face.power,
        toughness=face.toughness,
        loyalty=face.loyalty,
        defense=face.defense,
    )


def _parse_line(line: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(raw, dict):
        return None, "line is not a JSON object"
    return raw, None


def _key(raw: dict[str, Any] | None, *fields: str) -> str | None:
    if raw is None:
        return None
    values = [str(raw[f]) for f in fields if f in raw]
    return ":".join(values) or None


def load_cards(corpus: Corpus, path: Path) -> None:
    seen_ids: set[UUID] = set()
    for number, line in read_jsonl(path):
        corpus.seen["cards"] += 1
        raw, error = _parse_line(line)
        if raw is None:
            corpus.reject("cards", f"line {number}", error or "unreadable", {"line": line[:2000]})
            continue
        try:
            card = ScryfallCard.model_validate(raw)
        except ValidationError as exc:
            corpus.reject("cards", _key(raw, "oracle_id", "name"), str(exc), raw)
            continue
        if card.oracle_id in seen_ids:
            corpus.errors.append(f"duplicate oracle_id {card.oracle_id} ({card.name})")
            corpus.reject("cards", str(card.oracle_id), "duplicate oracle_id", raw)
            continue
        seen_ids.add(card.oracle_id)
        row, faces = card_rows(card, raw)
        corpus.cards.append(row)
        corpus.faces.extend(faces)


def load_rulings(corpus: Corpus, path: Path, known_cards: set[UUID]) -> None:
    for number, line in read_jsonl(path):
        corpus.seen["rulings"] += 1
        raw, error = _parse_line(line)
        if raw is None:
            corpus.reject("rulings", f"line {number}", error or "unreadable", {"line": line[:2000]})
            continue
        try:
            ruling = ScryfallRuling.model_validate(raw)
        except ValidationError as exc:
            corpus.reject("rulings", _key(raw, "oracle_id"), str(exc), raw)
            continue
        if ruling.oracle_id not in known_cards:
            corpus.reject("rulings", str(ruling.oracle_id), "unknown oracle_id", raw)
            continue
        corpus.rulings.append(
            RulingRow(ruling.oracle_id, ruling.source, ruling.published_at, ruling.comment)
        )


def load_tags(corpus: Corpus, path: Path, known_cards: set[UUID]) -> None:
    tags: list[OracleTag] = []
    raw_by_id: dict[UUID, dict[str, Any]] = {}
    slugs: set[str] = set()
    for number, line in read_jsonl(path):
        corpus.seen["tags"] += 1
        raw, error = _parse_line(line)
        if raw is None:
            corpus.reject("tags", f"line {number}", error or "unreadable", {"line": line[:2000]})
            continue
        try:
            tag = OracleTag.model_validate(raw)
        except ValidationError as exc:
            taggings = raw.get("taggings")
            # The tag's taggings are lost with it; count them so the ratio reflects that.
            if isinstance(taggings, list):
                corpus.seen["tags"] += len(taggings)
            summary = {k: v for k, v in raw.items() if k != "taggings"}
            corpus.reject("tags", _key(raw, "slug"), str(exc), summary)
            continue
        if tag.id in raw_by_id or tag.slug in slugs:
            corpus.errors.append(f"duplicate tag {tag.slug} ({tag.id})")
            corpus.reject("tags", tag.slug, "duplicate tag id or slug", {"id": str(tag.id)})
            continue
        raw_by_id[tag.id] = raw
        slugs.add(tag.slug)
        tags.append(tag)

    for tag in tags:
        corpus.tags.append(TagRow(tag.id, tag.slug, tag.label, tag.description, tag.aliases))
        tagged: set[UUID] = set()
        for raw_tagging in tag.taggings:
            corpus.seen["tags"] += 1
            key = f"{tag.slug}:{raw_tagging.get('oracle_id')}"
            try:
                tagging = Tagging.model_validate(raw_tagging)
            except ValidationError as exc:
                corpus.reject("tags", key, str(exc), raw_tagging)
                continue
            if tagging.oracle_id not in known_cards:
                corpus.reject("tags", key, "tagging has unknown oracle_id", raw_tagging)
                continue
            if tagging.oracle_id in tagged:
                corpus.reject("tags", key, "duplicate tagging", raw_tagging)
                continue
            tagged.add(tagging.oracle_id)
            corpus.card_tags.append(
                CardTagRow(tag.id, tagging.oracle_id, tagging.weight, tagging.annotation)
            )

    _load_tag_edges(corpus, tags)


def _load_tag_edges(corpus: Corpus, tags: list[OracleTag]) -> None:
    """Edges come from both parent_ids and child_ids; Tagger lists each edge on both ends."""
    known = {t.id: t.slug for t in tags}
    edges: set[tuple[UUID, UUID]] = set()
    for tag in tags:
        edges.update((tag.id, parent) for parent in tag.parent_ids)
        edges.update((child, tag.id) for child in tag.child_ids)
    for child, parent in sorted(edges):
        if child not in known or parent not in known or child == parent:
            corpus.reject(
                "tags",
                f"{known.get(child, child)}>{known.get(parent, parent)}",
                "tag edge points to an unknown tag or to itself",
                {"tag_id": str(child), "parent_id": str(parent)},
            )
            continue
        corpus.tag_edges.append(TagEdge(child, parent))
    cycle = _find_cycle(corpus.tag_edges)
    if cycle:
        corpus.errors.append("tag hierarchy has a cycle: " + " > ".join(known[t] for t in cycle))


def _find_cycle(edges: list[TagEdge]) -> list[UUID]:
    parents: dict[UUID, list[UUID]] = {}
    for e in edges:
        parents.setdefault(e.tag_id, []).append(e.parent_id)
    done: set[UUID] = set()
    for start in parents:
        if start in done:
            continue
        path: list[UUID] = []
        on_path: set[UUID] = set()
        stack: list[tuple[UUID, Iterator[UUID]]] = [(start, iter(parents.get(start, ())))]
        path.append(start)
        on_path.add(start)
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                stack.pop()
                path.pop()
                on_path.discard(node)
                done.add(node)
            elif nxt in on_path:
                return [*path[path.index(nxt) :], nxt]
            elif nxt not in done:
                stack.append((nxt, iter(parents.get(nxt, ()))))
                path.append(nxt)
                on_path.add(nxt)
    return []


def build_corpus(cards: Path, rulings: Path, tags: Path) -> Corpus:
    corpus = Corpus()
    load_cards(corpus, cards)
    known = {c.oracle_id for c in corpus.cards}
    load_rulings(corpus, rulings, known)
    load_tags(corpus, tags, known)
    return corpus
