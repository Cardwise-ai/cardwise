"""Grounding: answers may link only cards that a tool returned in this turn (spec 7.4).

The model cites cards as `[[<oracle_id>|<name>]]`. As its text streams, `RefFilter` rewrites
each citation before it reaches the client:

- the ID was returned by a tool this turn: kept, with our card name in place of the model's;
- `[[<name>]]` whose name matches a card returned this turn: linked to that card;
- anything else (invented, unseen or malformed ID): unlinked to the plain name.

Bare UUIDs in the text that no tool returned are removed, so an invented ID never reaches the
client in any form. Citations and IDs can be split across stream deltas, so the filter holds
back a possible partial citation or ID until it can decide. The cards event then lists the
linked cards in order of first citation.
"""

import re
from typing import Final
from uuid import UUID

from cardwise_api.models import CardRef
from cardwise_core.cards import MAX_CARD_NAME_LENGTH
from cardwise_core.search import CardHit

MAX_CARDS: Final = 100
"""Cards one answer can link (app.message_cards positions 0-99)."""

_UUID: Final = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
UUID_RE: Final = re.compile(_UUID)
REF_RE: Final = re.compile(
    rf"\[\[\s*(?:(?P<id>{_UUID})\s*(?:\|(?P<name>[^\[\]|\n]*))?|(?P<bare>[^\[\]|\n]+))\]\]"
)
UUID_LENGTH: Final = 36
MAX_REF_LENGTH: Final = 4 + UUID_LENGTH + 1 + MAX_CARD_NAME_LENGTH + 8
"""A `[[` that runs longer than this without closing is not a citation."""
_HEX_TAIL: Final = re.compile(r"[0-9a-fA-F-]+$")
"""Text ending like the start of a UUID is held back until the next delta."""


class Grounding:
    """Cards seen this turn and cards cited so far."""

    def __init__(self) -> None:
        self._seen: dict[UUID, CardRef] = {}
        self._by_name: dict[str, CardRef] = {}
        self._cited: dict[UUID, CardRef] = {}

    def add(self, hit: CardHit) -> None:
        ref = CardRef(oracle_id=hit.oracle_id, name=hit.name, image_uri=hit.image_uri)
        self._seen.setdefault(hit.oracle_id, ref)
        for name in (hit.name, *hit.name.split(" // ")):
            self._by_name.setdefault(_fold(name), ref)

    def seen(self, oracle_id: UUID) -> CardRef | None:
        return self._seen.get(oracle_id)

    def by_name(self, name: str) -> CardRef | None:
        return self._by_name.get(_fold(name))

    def cite(self, ref: CardRef) -> None:
        if len(self._cited) < MAX_CARDS:
            self._cited.setdefault(ref.oracle_id, ref)

    @property
    def cited(self) -> list[CardRef]:
        return list(self._cited.values())


def _fold(name: str) -> str:
    return " ".join(name.split()).casefold()


class RefFilter:
    """Rewrites citations in streamed text. Feed every delta, then flush at the end of a turn."""

    def __init__(self, grounding: Grounding) -> None:
        self._grounding = grounding
        self._pending = ""

    def feed(self, text: str) -> str:
        self._pending += text
        out: list[str] = []
        while self._pending:
            start = self._pending.find("[")
            if start < 0:
                out.append(self._release_plain(self._pending))
                break
            if start > 0:
                out.append(self._plain(self._pending[:start]))
                self._pending = self._pending[start:]
            if len(self._pending) < 2:
                break
            if self._pending[1] != "[":
                out.append("[")
                self._pending = self._pending[1:]
                continue
            end = self._pending.find("]]", 2)
            if end < 0:
                if len(self._pending) <= MAX_REF_LENGTH and "\n" not in self._pending:
                    break
                out.append("[")
                self._pending = self._pending[1:]
                continue
            match = REF_RE.fullmatch(self._pending[: end + 2])
            if match is None:
                out.append("[")
                self._pending = self._pending[1:]
                continue
            out.append(self._render(match))
            self._pending = self._pending[end + 2 :]
        return "".join(out)

    def flush(self) -> str:
        """Releases held text as plain text; an unfinished citation is not a citation."""
        text, self._pending = self._pending, ""
        return self._plain(text)

    def _release_plain(self, text: str) -> str:
        """Releases plain text, holding back a tail that may be the start of a UUID."""
        tail = _HEX_TAIL.search(text)
        if tail is None or len(tail.group()) >= UUID_LENGTH:
            self._pending = ""
            return self._plain(text)
        self._pending = text[tail.start() :]
        return self._plain(text[: tail.start()])

    def _plain(self, text: str) -> str:
        return UUID_RE.sub(self._keep_seen_id, text)

    def _keep_seen_id(self, match: re.Match[str]) -> str:
        return match.group() if self._grounding.seen(UUID(match.group())) else ""

    def _render(self, match: re.Match[str]) -> str:
        if match["bare"] is not None:
            name = match["bare"].strip()
            ref = self._grounding.by_name(name)
            return self._link(ref) if ref else self._plain(name)
        ref = self._grounding.seen(UUID(match["id"]))
        if ref is not None:
            return self._link(ref)
        return self._plain((match["name"] or "").strip())

    def _link(self, ref: CardRef) -> str:
        self._grounding.cite(ref)
        return f"[[{ref.oracle_id}|{ref.name}]]"
