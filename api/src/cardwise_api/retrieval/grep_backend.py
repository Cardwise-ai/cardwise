"""grepRAG: lexical card retrieval in Postgres (spec §6.2, ADR 0006).

Every statement reads only the active snapshot and is self-contained (the snapshot is resolved
in a CTE), so the backend works through the Supabase transaction pooler, where consecutive
statements may run on different server connections. Connections there must be opened with
`statement_cache_size=0`; the backend never owns connection settings and takes an `Executor`
from the caller.

Query text is built only from fixed fragments in this module. Every user value is a bind
parameter.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import asyncpg

from cardwise_api.models import Ruling
from cardwise_core.cards import Color
from cardwise_core.search import CardHit, CardLookup, CardQuery, RulingsLookup, SimilarQuery

Executor = asyncpg.Connection | asyncpg.Pool
"""A pool, or one connection. A single connection must not be shared by concurrent calls."""

SNAPSHOT_CTE: Final = "snap as (select id from corpus.snapshots where status = 'active')"
SNAPSHOT_ID: Final = "(select id from snap)"

HIT_COLUMNS: Final = """c.oracle_id,
    c.name,
    coalesce(c.mana_cost, '') as mana_cost,
    c.mana_value::float8 as mana_value,
    c.type_line,
    coalesce(c.oracle_text, '') as oracle_text,
    c.color_identity,
    c.image_uris ->> 'normal' as image_uri"""

POPULARITY: Final = "coalesce(1.0 / (1 + c.edhrec_rank / 1000.0), 0)::float8"
"""EDHREC rank mapped to (0, 1]: rank 1 is ~1, rank 1000 is 0.5, unranked is 0."""
POPULARITY_WEIGHT: Final = 0.25
"""Popularity breaks near-ties in relevance; it never outweighs a better text match."""

TYPE_WORD_SPLIT: Final = re.compile(r"[^a-z0-9']+")
"""Must match the pattern in TYPE_WORDS_SQL: type lines are compared word by word."""
TYPE_WORDS_SQL: Final = r"regexp_split_to_array(lower(c.type_line), '[^a-z0-9'']+')"
KEYWORDS_SQL: Final = "array(select lower(k) from unnest(c.keywords) k)"
"""Keywords compared case-insensitively; Scryfall writes them as `First strike`."""

ROLE_MATCHED_TAGS: Final = 8
"""matched_tags kept per similar-by-role hit, most specific (highest IDF) first."""
TEXT_CANDIDATES: Final = 200
"""similar-by-text reranks this many full-text candidates by lexeme overlap."""
LEGAL_STATUSES: Final = ("legal", "restricted")


@dataclass
class Params:
    """Collects bind values and hands out `$n` placeholders."""

    values: list[Any] = field(default_factory=list)

    def add(self, value: Any) -> str:
        self.values.append(value)
        return f"${len(self.values)}"


@dataclass(frozen=True, slots=True)
class Statement:
    sql: str
    params: tuple[Any, ...]


def type_words(types: Sequence[str]) -> list[str]:
    """Lowercased words from the requested types; every one must appear in the type line."""
    words = {w for t in types for w in TYPE_WORD_SPLIT.split(t.lower()) if w}
    return sorted(words)


def _mana(value: float) -> Decimal:
    return Decimal(str(value))


def _colors(colors: frozenset[Color]) -> list[str]:
    order = list(Color)
    return [str(c) for c in sorted(colors, key=order.index)]


def build_search(query: CardQuery) -> Statement:
    p = Params()
    ctes = [SNAPSHOT_CTE]
    joins: list[str] = []
    where = [f"c.snapshot_id = {SNAPSHOT_ID}", "c.is_game_card"]
    relevance = ["0::float8"]
    matched = "'{}'::text[]"
    recursive = False

    if query.text is not None:
        text = p.add(query.text)
        ctes.append(f"q as (select websearch_to_tsquery('english', {text}::text) as tsq)")
        joins.append("cross join q")
        where.append(f"(c.search_tsv @@ q.tsq or {text}::text operator(extensions.<%) c.name)")
        relevance.append("ts_rank_cd(c.search_tsv, q.tsq, 32)::float8")
        relevance.append(f"extensions.similarity(c.name, {text}::text)::float8")

    if query.tags:
        recursive = True
        slugs = sorted(set(query.tags))
        wanted = p.add(slugs)
        # A card has tag T when it is tagged with T or any descendant of T.
        ctes.append(
            f"""wanted(root, tag_id, slug) as (
        select t.slug, t.tag_id, t.slug
        from corpus.tags t
        where t.snapshot_id = {SNAPSHOT_ID} and t.slug = any({wanted}::text[])
        union
        select w.root, child.tag_id, child.slug
        from wanted w
        join corpus.tag_parents tp
            on tp.snapshot_id = {SNAPSHOT_ID} and tp.parent_id = w.tag_id
        join corpus.tags child
            on child.snapshot_id = tp.snapshot_id and child.tag_id = tp.tag_id
    )"""  # noqa: S608 (fixed fragments; slugs are a bind parameter)
        )
        ctes.append(
            f"""tag_hits as (
        select ct.oracle_id,
            array_agg(distinct w.slug order by w.slug) as slugs,
            count(distinct w.root) as roots
        from corpus.card_tags ct
        join wanted w on w.tag_id = ct.tag_id
        where ct.snapshot_id = {SNAPSHOT_ID}
        group by ct.oracle_id
    )"""  # noqa: S608 (fixed fragments)
        )
        joins.append(
            f"join tag_hits th on th.oracle_id = c.oracle_id and th.roots = {p.add(len(slugs))}"
        )
        matched = "th.slugs"

    if query.color_identity_within is not None:
        where.append(f"c.color_identity <@ {p.add(_colors(query.color_identity_within))}::text[]")
    if query.colors_include:
        where.append(f"c.color_identity @> {p.add(_colors(query.colors_include))}::text[]")
    if query.types:
        where.append(f"{TYPE_WORDS_SQL} @> {p.add(type_words(query.types))}::text[]")
    if query.keywords:
        keywords = sorted({k.lower() for k in query.keywords})
        where.append(f"{KEYWORDS_SQL} @> {p.add(keywords)}::text[]")
    if query.mana_value_min is not None:
        where.append(f"c.mana_value >= {p.add(_mana(query.mana_value_min))}::numeric")
    if query.mana_value_max is not None:
        where.append(f"c.mana_value <= {p.add(_mana(query.mana_value_max))}::numeric")
    if query.legal_in is not None:
        where.append(
            f"c.legalities ->> {p.add(query.legal_in.value)}::text"
            f" = any({p.add(list(LEGAL_STATUSES))}::text[])"
        )

    score = (
        f"round(({' + '.join(relevance)} + {POPULARITY_WEIGHT} * {POPULARITY})::numeric, 4)::float8"
    )
    # Fixed fragments only; every value above went through Params.
    sql = f"""with {"recursive " if recursive else ""}{", ".join(ctes)}
select {HIT_COLUMNS},
    {matched} as matched_tags,
    {score} as score
from corpus.cards c
{" ".join(joins)}
where {" and ".join(where)}
order by score desc, c.name, c.oracle_id
limit {p.add(query.limit)}"""  # noqa: S608
    return Statement(sql, tuple(p.values))


def build_similar(query: SimilarQuery) -> Statement:
    return _similar_by_role(query) if query.by == "role" else _similar_by_text(query)


def _color_filter(p: Params, colors: frozenset[Color] | None) -> str:
    if colors is None:
        return ""
    return f" and c.color_identity <@ {p.add(_colors(colors))}::text[]"


def _similar_by_role(query: SimilarQuery) -> Statement:
    """Shared Tagger tags weighted by IDF, normalized by the source card's total weight.

    A card's role set is its direct tags plus their parents, so siblings such as mana-dork
    and mana-rock meet at mana-producer. Going one level up keeps broad roots out.
    """
    p = Params()
    source = p.add(query.oracle_id)
    colors = _color_filter(p, query.color_identity_within)
    sql = f"""with {SNAPSHOT_CTE},
src_direct as (
    select ct.tag_id from corpus.card_tags ct
    where ct.snapshot_id = {SNAPSHOT_ID} and ct.oracle_id = {source}::uuid
),
src_role as (
    select tag_id from src_direct
    union
    select tp.parent_id from corpus.tag_parents tp
    join src_direct d on d.tag_id = tp.tag_id
    where tp.snapshot_id = {SNAPSHOT_ID}
),
holders as (
    select ct.oracle_id, ct.tag_id from corpus.card_tags ct
    join src_role r on r.tag_id = ct.tag_id
    where ct.snapshot_id = {SNAPSHOT_ID}
    union
    select ct.oracle_id, tp.parent_id from corpus.card_tags ct
    join corpus.tag_parents tp on tp.snapshot_id = ct.snapshot_id and tp.tag_id = ct.tag_id
    join src_role r on r.tag_id = tp.parent_id
    where ct.snapshot_id = {SNAPSHOT_ID}
),
game_cards as (
    select count(*)::float8 as n from corpus.cards
    where snapshot_id = {SNAPSHOT_ID} and is_game_card
),
weights as (
    select h.tag_id, ln(1 + (select n from game_cards) / count(*)) as idf
    from holders h group by h.tag_id
),
total as (select sum(idf) as w from weights),
cand as (
    select h.oracle_id,
        sum(w.idf) as shared,
        array_agg(t.slug order by w.idf desc, t.slug) as slugs
    from holders h
    join weights w on w.tag_id = h.tag_id
    join corpus.tags t on t.snapshot_id = {SNAPSHOT_ID} and t.tag_id = h.tag_id
    where h.oracle_id <> {source}::uuid
    group by h.oracle_id
)
select {HIT_COLUMNS},
    cand.slugs[1:{ROLE_MATCHED_TAGS}] as matched_tags,
    round((cand.shared / nullif(total.w, 0))::numeric, 4)::float8 as score
from cand
cross join total
join corpus.cards c on c.snapshot_id = {SNAPSHOT_ID} and c.oracle_id = cand.oracle_id
where c.is_game_card{colors}
order by score desc, c.edhrec_rank nulls last, c.name, c.oracle_id
limit {p.add(query.limit)}"""  # noqa: S608
    return Statement(sql, tuple(p.values))


def _similar_by_text(query: SimilarQuery) -> Statement:
    """Full-text OR over the source's rules-text lexemes, reranked by lexeme Jaccard overlap.

    Type line and rules text only: names would make cards similar for sharing a word.
    """
    p = Params()
    source = p.add(query.oracle_id)
    colors = _color_filter(p, query.color_identity_within)
    lexemes = (
        "tsvector_to_array(to_tsvector('english', concat_ws(' ', c.type_line, c.oracle_text)))"
    )
    sql = f"""with {SNAPSHOT_CTE},
src as (
    select {lexemes} as lex
    from corpus.cards c
    where c.snapshot_id = {SNAPSHOT_ID} and c.oracle_id = {source}::uuid
),
q as (
    select string_agg('''' || l || '''', ' | ')::tsquery as tsq
    from src, unnest(src.lex) l
    where l ~ '^\\w+$'
),
cand as (
    select c.oracle_id
    from corpus.cards c
    cross join q
    where c.snapshot_id = {SNAPSHOT_ID}
        and c.is_game_card
        and c.oracle_id <> {source}::uuid
        and c.search_tsv @@ q.tsq{colors}
    order by ts_rank(c.search_tsv, q.tsq, 1) desc, c.oracle_id
    limit {TEXT_CANDIDATES}
),
scored as (
    select cand.oracle_id,
        (select count(*) from (
            select unnest({lexemes}) intersect select unnest(src.lex)) i)::float8
        / nullif((select count(*) from (
            select unnest({lexemes}) union select unnest(src.lex)) u), 0)
        as jaccard
    from cand
    cross join src
    join corpus.cards c on c.snapshot_id = {SNAPSHOT_ID} and c.oracle_id = cand.oracle_id
)
select {HIT_COLUMNS},
    '{{}}'::text[] as matched_tags,
    round(coalesce(s.jaccard, 0)::numeric, 4)::float8 as score
from scored s
join corpus.cards c on c.snapshot_id = {SNAPSHOT_ID} and c.oracle_id = s.oracle_id
order by score desc, c.edhrec_rank nulls last, c.name, c.oracle_id
limit {p.add(query.limit)}"""  # noqa: S608
    return Statement(sql, tuple(p.values))


EXACT_NAME_SCORE: Final = 1.0
CASELESS_NAME_SCORE: Final = 0.95
FACE_NAME_SCORE: Final = 0.9
FUZZY_SCALE: Final = 0.8
"""Fuzzy matches score at most this, so any exact or face match wins."""


def build_lookup(query: CardLookup) -> Statement:
    """Oracle ID, or name: exact, then case-insensitive, then a face name, then trigram."""
    p = Params()
    if query.oracle_id is not None:
        sql = f"""with {SNAPSHOT_CTE}
select {HIT_COLUMNS},
    '{{}}'::text[] as matched_tags,
    {EXACT_NAME_SCORE}::float8 as score
from corpus.cards c
where c.snapshot_id = {SNAPSHOT_ID} and c.oracle_id = {p.add(query.oracle_id)}::uuid"""  # noqa: S608
        return Statement(sql, tuple(p.values))

    name = p.add(query.name)
    sql = f"""with {SNAPSHOT_CTE},
cand as (
    select c.oracle_id from corpus.cards c
    where c.snapshot_id = {SNAPSHOT_ID} and lower(c.name) = lower({name}::text)
    union
    select f.oracle_id from corpus.card_faces f
    where f.snapshot_id = {SNAPSHOT_ID} and lower(f.name) = lower({name}::text)
    union
    select c.oracle_id from corpus.cards c
    where c.snapshot_id = {SNAPSHOT_ID}
        and (c.name operator(extensions.%) {name}::text
            or {name}::text operator(extensions.<%) c.name)
),
scored as (
    select cand.oracle_id,
        case
            when c.name = {name}::text then {EXACT_NAME_SCORE}
            when lower(c.name) = lower({name}::text) then {CASELESS_NAME_SCORE}
            when exists (
                select 1 from corpus.card_faces f
                where f.snapshot_id = c.snapshot_id and f.oracle_id = c.oracle_id
                    and lower(f.name) = lower({name}::text)
            ) then {FACE_NAME_SCORE}
            else {FUZZY_SCALE} * greatest(
                extensions.similarity(c.name, {name}::text),
                0.9 * extensions.word_similarity({name}::text, c.name)
            )
        end::float8 as score
    from cand
    join corpus.cards c on c.snapshot_id = {SNAPSHOT_ID} and c.oracle_id = cand.oracle_id
)
select {HIT_COLUMNS},
    '{{}}'::text[] as matched_tags,
    round(s.score::numeric, 4)::float8 as score
from scored s
join corpus.cards c on c.snapshot_id = {SNAPSHOT_ID} and c.oracle_id = s.oracle_id
order by score desc, c.is_game_card desc, c.edhrec_rank nulls last, c.name, c.oracle_id
limit 1"""  # noqa: S608
    return Statement(sql, tuple(p.values))


def build_rulings(query: RulingsLookup) -> Statement:
    p = Params()
    sql = f"""with {SNAPSHOT_CTE}
select r.published_at, r.source, r.comment
from corpus.rulings r
where r.snapshot_id = {SNAPSHOT_ID} and r.oracle_id = {p.add(query.oracle_id)}::uuid
order by r.published_at, r.id"""  # noqa: S608
    return Statement(sql, tuple(p.values))


def to_hit(row: asyncpg.Record) -> CardHit:
    oracle_id: UUID = row["oracle_id"]
    return CardHit(
        oracle_id=oracle_id,
        name=row["name"],
        mana_cost=row["mana_cost"],
        mana_value=row["mana_value"],
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
        color_identity=tuple(Color(c) for c in row["color_identity"]),
        image_uri=row["image_uri"],
        matched_tags=tuple(row["matched_tags"]),
        score=row["score"],
    )


class GrepSearchBackend:
    """SearchBackend over Postgres full-text search, trigram names and Tagger tags."""

    def __init__(self, db: Executor) -> None:
        self._db = db

    @property
    def name(self) -> str:
        return "grep"

    async def _fetch(self, statement: Statement) -> list[asyncpg.Record]:
        return await self._db.fetch(statement.sql, *statement.params)

    async def search(self, query: CardQuery) -> list[CardHit]:
        return [to_hit(r) for r in await self._fetch(build_search(query))]

    async def similar(self, query: SimilarQuery) -> list[CardHit]:
        return [to_hit(r) for r in await self._fetch(build_similar(query))]

    async def get_card(self, query: CardLookup) -> CardHit | None:
        """The best match for the lookup, or None. `score` says how the name matched."""
        rows = await self._fetch(build_lookup(query))
        return to_hit(rows[0]) if rows else None

    async def get_rulings(self, query: RulingsLookup) -> list[Ruling]:
        """Oldest first. Empty for unknown cards and cards without rulings."""
        rows = await self._fetch(build_rulings(query))
        return [
            Ruling(published_at=r["published_at"], source=r["source"], text=r["comment"])
            for r in rows
        ]
