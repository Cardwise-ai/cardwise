"""Chat storage. Every method takes the caller's user ID and filters on it.

The API connects to Postgres as a role that bypasses RLS, so these filters are the access
control: a chat that exists but belongs to someone else looks exactly like a missing one.
"""

import base64
import binascii
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final, Literal, Protocol
from uuid import UUID, uuid4

import asyncpg

from cardwise_api.models import CardRef, ChatOut, ChatPage, MessageOut, MessagePage

MAX_MESSAGE_CARDS: Final = 100
MAX_STORED_CONTENT: Final = 20_000

MessageStatus = Literal["complete", "interrupted", "failed"]


class InvalidCursorError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Position:
    """Keyset position: the sort timestamp and ID of the last row on the previous page."""

    at: datetime
    id: UUID

    def encode(self) -> str:
        raw = f"{self.at.isoformat()}|{self.id}".encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @classmethod
    def decode(cls, cursor: str) -> "Position":
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
            at, _, id_ = raw.partition("|")
            parsed = datetime.fromisoformat(at)
            if parsed.tzinfo is None:
                raise InvalidCursorError("cursor timestamp has no time zone")
            return cls(at=parsed, id=UUID(id_))
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise InvalidCursorError("malformed cursor") from exc


@dataclass(frozen=True, slots=True)
class AssistantReply:
    id: UUID
    content: str
    status: MessageStatus
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cards: tuple[CardRef, ...] = ()


class ChatRepository(Protocol):
    async def create_chat(self, user_id: UUID, title: str) -> ChatOut: ...

    async def list_chats(self, user_id: UUID, after: Position | None, limit: int) -> ChatPage:
        """Newest activity first (`updated_at` desc)."""
        ...

    async def get_chat(self, user_id: UUID, chat_id: UUID) -> ChatOut | None: ...

    async def rename_chat(self, user_id: UUID, chat_id: UUID, title: str) -> ChatOut | None: ...

    async def delete_chat(self, user_id: UUID, chat_id: UUID) -> bool: ...

    async def list_messages(
        self, user_id: UUID, chat_id: UUID, after: Position | None, limit: int
    ) -> MessagePage | None:
        """Oldest first. None when the chat does not exist for this user."""
        ...

    async def recent_messages(
        self, user_id: UUID, chat_id: UUID, limit: int
    ) -> list[MessageOut] | None:
        """The last `limit` messages, oldest first, without cards. For model context."""
        ...

    async def add_user_message(
        self, user_id: UUID, chat_id: UUID, content: str
    ) -> MessageOut | None: ...

    async def add_assistant_message(
        self, user_id: UUID, chat_id: UUID, reply: AssistantReply
    ) -> MessageOut | None: ...


def _unique_cards(cards: tuple[CardRef, ...]) -> list[CardRef]:
    seen: set[UUID] = set()
    unique: list[CardRef] = []
    for card in cards:
        if card.oracle_id not in seen:
            seen.add(card.oracle_id)
            unique.append(card)
    return unique[:MAX_MESSAGE_CARDS]


def _page_cursor(keys: list[tuple[datetime, UUID]], limit: int) -> str | None:
    """`keys` holds up to limit + 1 rows; a row past the limit means there is another page."""
    if len(keys) <= limit:
        return None
    at, id_ = keys[limit - 1]
    return Position(at, id_).encode()


# Postgres ---------------------------------------------------------------------------------

_CHAT_COLUMNS: Final = "id, title, created_at, updated_at"
_MESSAGE_COLUMNS: Final = "m.id, m.role, m.content, m.status, m.created_at"


def _chat(row: asyncpg.Record) -> ChatOut:
    return ChatOut(
        id=row["id"], title=row["title"], created_at=row["created_at"], updated_at=row["updated_at"]
    )


def _message(row: asyncpg.Record, cards: list[CardRef] | None = None) -> MessageOut:
    return MessageOut(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        status=row["status"],
        cards=cards or [],
        created_at=row["created_at"],
    )


class PgChatRepository:
    # Timestamps use clock_timestamp(), not now(), so rows written inside one transaction
    # still sort in the order they were written.
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create_chat(self, user_id: UUID, title: str) -> ChatOut:
        row = await self._conn.fetchrow(
            "insert into app.chats (user_id, title, created_at, updated_at)"  # noqa: S608
            " values ($1, $2, clock_timestamp(), clock_timestamp())"
            f" returning {_CHAT_COLUMNS}",
            user_id,
            title,
        )
        if row is None:  # pragma: no cover - insert ... returning always yields a row
            raise RuntimeError("insert returned no row")
        return _chat(row)

    async def list_chats(self, user_id: UUID, after: Position | None, limit: int) -> ChatPage:
        rows = await self._conn.fetch(
            f"select {_CHAT_COLUMNS} from app.chats"  # noqa: S608
            " where user_id = $1"
            " and ($2::timestamptz is null or (updated_at, id) < ($2::timestamptz, $3::uuid))"
            " order by updated_at desc, id desc limit $4",
            user_id,
            after.at if after else None,
            after.id if after else None,
            limit + 1,
        )
        return ChatPage(
            items=[_chat(r) for r in rows[:limit]],
            next_cursor=_page_cursor([(r["updated_at"], r["id"]) for r in rows], limit),
        )

    async def get_chat(self, user_id: UUID, chat_id: UUID) -> ChatOut | None:
        row = await self._conn.fetchrow(
            f"select {_CHAT_COLUMNS} from app.chats where id = $2 and user_id = $1",  # noqa: S608
            user_id,
            chat_id,
        )
        return None if row is None else _chat(row)

    async def rename_chat(self, user_id: UUID, chat_id: UUID, title: str) -> ChatOut | None:
        row = await self._conn.fetchrow(
            "update app.chats set title = $3, updated_at = clock_timestamp()"  # noqa: S608
            f" where id = $2 and user_id = $1 returning {_CHAT_COLUMNS}",
            user_id,
            chat_id,
            title,
        )
        return None if row is None else _chat(row)

    async def delete_chat(self, user_id: UUID, chat_id: UUID) -> bool:
        deleted = await self._conn.fetchval(
            "delete from app.chats where id = $2 and user_id = $1 returning id", user_id, chat_id
        )
        return deleted is not None

    async def _owns(self, user_id: UUID, chat_id: UUID) -> bool:
        found = await self._conn.fetchval(
            "select true from app.chats where id = $2 and user_id = $1", user_id, chat_id
        )
        return found is True

    async def list_messages(
        self, user_id: UUID, chat_id: UUID, after: Position | None, limit: int
    ) -> MessagePage | None:
        if not await self._owns(user_id, chat_id):
            return None
        rows = await self._conn.fetch(
            f"select {_MESSAGE_COLUMNS} from app.messages m"  # noqa: S608
            " join app.chats c on c.id = m.chat_id"
            " where m.chat_id = $2 and c.user_id = $1"
            " and ($3::timestamptz is null or (m.created_at, m.id) > ($3::timestamptz, $4::uuid))"
            " order by m.created_at, m.id limit $5",
            user_id,
            chat_id,
            after.at if after else None,
            after.id if after else None,
            limit + 1,
        )
        page = rows[:limit]
        cards = await self._cards([r["id"] for r in page])
        return MessagePage(
            items=[_message(r, cards.get(r["id"])) for r in page],
            next_cursor=_page_cursor([(r["created_at"], r["id"]) for r in rows], limit),
        )

    async def _cards(self, message_ids: list[UUID]) -> dict[UUID, list[CardRef]]:
        """Stored card links, with today's image from the active snapshot when it has the card."""
        if not message_ids:
            return {}
        rows = await self._conn.fetch(
            "select mc.message_id, mc.oracle_id, mc.name, c.image_uris ->> 'normal' as image_uri"
            " from app.message_cards mc"
            " left join corpus.snapshots s on s.status = 'active'"
            " left join corpus.cards c on c.snapshot_id = s.id and c.oracle_id = mc.oracle_id"
            " where mc.message_id = any($1::uuid[])"
            " order by mc.message_id, mc.position",
            message_ids,
        )
        cards: dict[UUID, list[CardRef]] = {}
        for r in rows:
            cards.setdefault(r["message_id"], []).append(
                CardRef(oracle_id=r["oracle_id"], name=r["name"], image_uri=r["image_uri"])
            )
        return cards

    async def recent_messages(
        self, user_id: UUID, chat_id: UUID, limit: int
    ) -> list[MessageOut] | None:
        if not await self._owns(user_id, chat_id):
            return None
        rows = await self._conn.fetch(
            f"select {_MESSAGE_COLUMNS} from app.messages m"  # noqa: S608
            " join app.chats c on c.id = m.chat_id"
            " where m.chat_id = $2 and c.user_id = $1"
            " order by m.created_at desc, m.id desc limit $3",
            user_id,
            chat_id,
            limit,
        )
        return [_message(r) for r in reversed(rows)]

    async def add_user_message(
        self, user_id: UUID, chat_id: UUID, content: str
    ) -> MessageOut | None:
        row = await self._conn.fetchrow(
            "with chat as ("  # noqa: S608
            " update app.chats set updated_at = clock_timestamp()"
            " where id = $2 and user_id = $1 returning id)"
            " insert into app.messages as m (chat_id, role, content, created_at)"
            " select id, 'user', $3, clock_timestamp() from chat"
            f" returning {_MESSAGE_COLUMNS}",
            user_id,
            chat_id,
            content,
        )
        return None if row is None else _message(row)

    async def add_assistant_message(
        self, user_id: UUID, chat_id: UUID, reply: AssistantReply
    ) -> MessageOut | None:
        cards = _unique_cards(reply.cards)
        usage = json.dumps(
            {"input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens}
        )
        async with self._conn.transaction():
            row = await self._conn.fetchrow(
                "with chat as ("  # noqa: S608
                " update app.chats set updated_at = clock_timestamp()"
                " where id = $2 and user_id = $1 returning id)"
                " insert into app.messages as m"
                " (id, chat_id, role, content, status, model, usage, created_at)"
                " select $3, id, 'assistant', $4, $5, $6, $7::jsonb, clock_timestamp() from chat"
                f" returning {_MESSAGE_COLUMNS}",
                user_id,
                chat_id,
                reply.id,
                reply.content[:MAX_STORED_CONTENT],
                reply.status,
                reply.model,
                usage,
            )
            if row is None:
                return None
            if cards:
                await self._conn.execute(
                    "insert into app.message_cards (message_id, position, oracle_id, name)"
                    " select $1, t.ord - 1, t.oracle_id, t.name"
                    " from unnest($2::uuid[], $3::text[]) with ordinality"
                    " as t(oracle_id, name, ord)",
                    reply.id,
                    [c.oracle_id for c in cards],
                    [c.name for c in cards],
                )
        return _message(row, cards)


# In memory (tests, local runs without a database) -----------------------------------------


@dataclass
class _StoredChat:
    user_id: UUID
    chat: ChatOut


@dataclass
class _StoredMessage:
    chat_id: UUID
    message: MessageOut


@dataclass
class InMemoryChatStore:
    """Shared state behind InMemoryChatRepository; one per app."""

    chats: dict[UUID, _StoredChat] = field(default_factory=dict)
    messages: list[_StoredMessage] = field(default_factory=list)
    _last: datetime = field(default_factory=lambda: datetime.min.replace(tzinfo=UTC))

    def now(self) -> datetime:
        """Strictly increasing, so ordering is deterministic even within one clock tick."""
        self._last = max(datetime.now(UTC), self._last + timedelta(microseconds=1))
        return self._last


class InMemoryChatRepository:
    def __init__(self, store: InMemoryChatStore) -> None:
        self._s = store

    def _owned(self, user_id: UUID, chat_id: UUID) -> ChatOut | None:
        stored = self._s.chats.get(chat_id)
        return stored.chat if stored and stored.user_id == user_id else None

    def _touch(self, chat_id: UUID) -> None:
        stored = self._s.chats[chat_id]
        stored.chat = stored.chat.model_copy(update={"updated_at": self._s.now()})

    async def create_chat(self, user_id: UUID, title: str) -> ChatOut:
        now = self._s.now()
        chat = ChatOut(id=uuid4(), title=title, created_at=now, updated_at=now)
        self._s.chats[chat.id] = _StoredChat(user_id, chat)
        return chat

    async def list_chats(self, user_id: UUID, after: Position | None, limit: int) -> ChatPage:
        chats = sorted(
            (s.chat for s in self._s.chats.values() if s.user_id == user_id),
            key=lambda c: (c.updated_at, c.id),
            reverse=True,
        )
        if after:
            chats = [c for c in chats if (c.updated_at, c.id) < (after.at, after.id)]
        return ChatPage(
            items=chats[:limit],
            next_cursor=_page_cursor([(c.updated_at, c.id) for c in chats[: limit + 1]], limit),
        )

    async def get_chat(self, user_id: UUID, chat_id: UUID) -> ChatOut | None:
        return self._owned(user_id, chat_id)

    async def rename_chat(self, user_id: UUID, chat_id: UUID, title: str) -> ChatOut | None:
        chat = self._owned(user_id, chat_id)
        if chat is None:
            return None
        renamed = chat.model_copy(update={"title": title, "updated_at": self._s.now()})
        self._s.chats[chat_id].chat = renamed
        return renamed

    async def delete_chat(self, user_id: UUID, chat_id: UUID) -> bool:
        if self._owned(user_id, chat_id) is None:
            return False
        del self._s.chats[chat_id]
        self._s.messages = [m for m in self._s.messages if m.chat_id != chat_id]
        return True

    def _chat_messages(self, chat_id: UUID) -> list[MessageOut]:
        return sorted(
            (m.message for m in self._s.messages if m.chat_id == chat_id),
            key=lambda m: (m.created_at, m.id),
        )

    async def list_messages(
        self, user_id: UUID, chat_id: UUID, after: Position | None, limit: int
    ) -> MessagePage | None:
        if self._owned(user_id, chat_id) is None:
            return None
        messages = self._chat_messages(chat_id)
        if after:
            messages = [m for m in messages if (m.created_at, m.id) > (after.at, after.id)]
        return MessagePage(
            items=messages[:limit],
            next_cursor=_page_cursor([(m.created_at, m.id) for m in messages[: limit + 1]], limit),
        )

    async def recent_messages(
        self, user_id: UUID, chat_id: UUID, limit: int
    ) -> list[MessageOut] | None:
        if self._owned(user_id, chat_id) is None:
            return None
        return [m.model_copy(update={"cards": []}) for m in self._chat_messages(chat_id)[-limit:]]

    async def add_user_message(
        self, user_id: UUID, chat_id: UUID, content: str
    ) -> MessageOut | None:
        if self._owned(user_id, chat_id) is None:
            return None
        message = MessageOut(
            id=uuid4(),
            role="user",
            content=content,
            status="complete",
            cards=[],
            created_at=self._s.now(),
        )
        self._s.messages.append(_StoredMessage(chat_id, message))
        self._touch(chat_id)
        return message

    async def add_assistant_message(
        self, user_id: UUID, chat_id: UUID, reply: AssistantReply
    ) -> MessageOut | None:
        if self._owned(user_id, chat_id) is None:
            return None
        message = MessageOut(
            id=reply.id,
            role="assistant",
            content=reply.content[:MAX_STORED_CONTENT],
            status=reply.status,
            cards=_unique_cards(reply.cards),
            created_at=self._s.now(),
        )
        self._s.messages.append(_StoredMessage(chat_id, message))
        self._touch(chat_id)
        return message
