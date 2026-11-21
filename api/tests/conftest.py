"""Shared API test fixtures.

Auth: a signing key, its JWKS and token factory, and app harnesses with a scripted agent.

Database (retrieval): the ingest fixture corpus loaded through the real loader. Two snapshots
are loaded: a first one with an extra card that only it has, then the normal fixture corpus,
which retires the first. Tests must never see the extra card.
"""

import hashlib
import os
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from cardwise_api.agent.port import Agent
from cardwise_api.retrieval import CardBackend, GrepSearchBackend
from cardwise_api.settings import Settings
from cardwise_api.testing import (
    FakeJwks,
    Harness,
    ScriptedAgent,
    SigningKey,
    Tokens,
    ec_key,
    make_harness,
)
from cardwise_ingest import load
from cardwise_ingest.transform import CardTagRow, Corpus, build_corpus


@pytest.fixture(scope="session")
def signing_key() -> SigningKey:
    return ec_key()


@pytest.fixture
def jwks(signing_key: SigningKey) -> FakeJwks:
    return FakeJwks([signing_key])


@pytest.fixture
def tokens(signing_key: SigningKey) -> Tokens:
    return Tokens(signing_key)


HarnessFactory = Callable[..., Harness]


@pytest.fixture
def new_harness(tokens: Tokens, jwks: FakeJwks) -> Iterator[HarnessFactory]:
    made: list[Harness] = []

    def make(
        *,
        agent: Agent | None = None,
        backend: CardBackend | None = None,
        settings: Settings | None = None,
    ) -> Harness:
        harness = make_harness(tokens, jwks, agent=agent, backend=backend, settings=settings)
        made.append(harness)
        return harness

    yield make
    for harness in made:
        harness.client.close()


@pytest.fixture
def harness(new_harness: HarnessFactory) -> Harness:
    return new_harness(agent=ScriptedAgent())


DSN = os.environ.get(
    "CARDWISE_TEST_DB_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)
INGEST_FIXTURES = Path(__file__).parents[2] / "ingest" / "tests" / "fixtures"
RETIRED_ONLY_ID = UUID("0badcafe-0000-4000-8000-000000000001")
RETIRED_ONLY_NAME = "Zhalfirin Retired Relic"


def fixture_corpus() -> Corpus:
    return build_corpus(
        INGEST_FIXTURES / "cards.jsonl",
        INGEST_FIXTURES / "rulings.jsonl",
        INGEST_FIXTURES / "oracle_tags.jsonl",
    )


def retired_corpus() -> Corpus:
    """The fixture corpus plus a mana rock that exists only in the retired snapshot."""
    corpus = fixture_corpus()
    sol_ring = next(c for c in corpus.cards if c.name == "Sol Ring")
    corpus.cards.append(
        replace(
            sol_ring,
            oracle_id=RETIRED_ONLY_ID,
            name=RETIRED_ONLY_NAME,
            search_text=f"{RETIRED_ONLY_NAME}\nArtifact\n{{T}}: Add {{C}}{{C}}.",
        )
    )
    mana_rock = next(t for t in corpus.tags if t.slug == "mana-rock")
    corpus.card_tags.append(CardTagRow(mana_rock.tag_id, RETIRED_ONLY_ID, "median", None))
    return corpus


async def load_and_activate(conn: asyncpg.Connection, corpus: Corpus, seq: int) -> int:
    snapshot_id: int = await conn.fetchval(
        "insert into corpus.snapshots (source_updated_at, content_sha256, source_files)"
        " values (now(), $1, '{}'::jsonb) returning id",
        hashlib.sha256(f"retrieval-test-{seq}".encode()).hexdigest(),
    )
    await load.load_rows(conn, snapshot_id, corpus)
    await load.activate(conn, snapshot_id, None)
    return snapshot_id


@pytest.fixture
async def corpus_db() -> AsyncIterator[asyncpg.Connection]:
    # statement_cache_size=0 as through the Supabase transaction pooler.
    conn = await asyncpg.connect(DSN, statement_cache_size=0)
    before: int = await conn.fetchval("select coalesce(max(id), 0) from corpus.snapshots")
    if await conn.fetchval("select count(*) from corpus.snapshots where status = 'active'"):
        await conn.close()
        pytest.skip("database already has an active snapshot")
    try:
        await load_and_activate(conn, retired_corpus(), 1)
        await load_and_activate(conn, fixture_corpus(), 2)
        yield conn
    finally:
        await conn.execute("delete from corpus.snapshots where id > $1", before)
        await conn.close()


@pytest.fixture
def backend(corpus_db: asyncpg.Connection) -> GrepSearchBackend:
    return GrepSearchBackend(corpus_db)


@pytest.fixture
def retired_only() -> tuple[UUID, str]:
    return RETIRED_ONLY_ID, RETIRED_ONLY_NAME
