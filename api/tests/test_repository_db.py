"""PgChatRepository against the local database. Each test runs in a rolled-back transaction."""

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import asyncpg
import pytest

from cardwise_api.chats.repository import AssistantReply, PgChatRepository, Position
from cardwise_api.models import CardRef

pytestmark = pytest.mark.db

DSN = os.environ.get(
    "CARDWISE_TEST_DB_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)


@pytest.fixture
async def conn() -> AsyncIterator[asyncpg.Connection]:
    # statement_cache_size=0 as in production, so the queries are known to run unprepared.
    connection = await asyncpg.connect(DSN, statement_cache_size=0)
    tx = connection.transaction()
    await tx.start()
    try:
        yield connection
    finally:
        await tx.rollback()
        await connection.close()


async def new_user(conn: asyncpg.Connection) -> UUID:
    user_id = uuid4()
    await conn.execute(
        "insert into auth.users (id, email) values ($1, $2)", user_id, f"{user_id}@test.invalid"
    )
    return user_id


async def test_chat_crud_is_scoped_to_the_owner(conn: asyncpg.Connection) -> None:
    repo = PgChatRepository(conn)
    alice, bob = await new_user(conn), await new_user(conn)
    chat = await repo.create_chat(alice, "Ramp")

    assert await repo.get_chat(alice, chat.id) == chat
    assert await repo.get_chat(bob, chat.id) is None
    assert await repo.rename_chat(bob, chat.id, "mine") is None
    assert not await repo.delete_chat(bob, chat.id)
    assert await repo.list_messages(bob, chat.id, None, 10) is None
    assert await repo.recent_messages(bob, chat.id, 10) is None
    assert await repo.add_user_message(bob, chat.id, "hi") is None
    reply = AssistantReply(id=uuid4(), content="x", status="complete")
    assert await repo.add_assistant_message(bob, chat.id, reply) is None
    assert (await repo.list_chats(bob, None, 10)).items == []

    renamed = await repo.rename_chat(alice, chat.id, "Elves")
    assert renamed is not None
    assert renamed.title == "Elves"
    assert renamed.updated_at > chat.updated_at
    assert await repo.delete_chat(alice, chat.id)
    assert await repo.get_chat(alice, chat.id) is None


async def test_chats_page_newest_activity_first(conn: asyncpg.Connection) -> None:
    repo = PgChatRepository(conn)
    user = await new_user(conn)
    chats = [await repo.create_chat(user, f"chat {i}") for i in range(3)]
    await repo.add_user_message(user, chats[0].id, "bump")

    first = await repo.list_chats(user, None, 2)
    assert [c.id for c in first.items] == [chats[0].id, chats[2].id]
    assert first.next_cursor is not None
    rest = await repo.list_chats(user, Position.decode(first.next_cursor), 2)
    assert [c.id for c in rest.items] == [chats[1].id]
    assert rest.next_cursor is None


async def test_messages_with_cards_round_trip(conn: asyncpg.Connection) -> None:
    repo = PgChatRepository(conn)
    user = await new_user(conn)
    chat = await repo.create_chat(user, "Ramp")
    question = await repo.add_user_message(user, chat.id, "Best green ramp?")
    assert question is not None

    elves = CardRef(oracle_id=uuid4(), name="Llanowar Elves", image_uri=None)
    birds = CardRef(oracle_id=uuid4(), name="Birds of Paradise", image_uri=None)
    reply = AssistantReply(
        id=uuid4(),
        content="Try these.",
        status="interrupted",
        model="fake/model",
        input_tokens=10,
        output_tokens=2,
        cards=(elves, birds, elves),
    )
    answer = await repo.add_assistant_message(user, chat.id, reply)
    assert answer is not None
    assert answer.cards == [elves, birds]

    page = await repo.list_messages(user, chat.id, None, 1)
    assert page is not None
    assert [m.id for m in page.items] == [question.id]
    assert page.next_cursor is not None
    rest = await repo.list_messages(user, chat.id, Position.decode(page.next_cursor), 10)
    assert rest is not None
    assert rest.items == [answer]

    row = await conn.fetchrow("select model, usage from app.messages where id = $1", reply.id)
    assert row is not None
    assert row["model"] == "fake/model"
    assert '"output_tokens": 2' in row["usage"]

    recent = await repo.recent_messages(user, chat.id, 1)
    assert recent is not None
    assert [m.content for m in recent] == ["Try these."]

    assert await repo.delete_chat(user, chat.id)
    assert (
        await conn.fetchval(
            "select count(*) from app.message_cards where message_id = $1", reply.id
        )
        == 0
    )
