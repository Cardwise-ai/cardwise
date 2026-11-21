"""Server-sent events for the message stream (spec 7.3).

`sse_body` turns StreamEvents into SSE frames and sends a comment line when nothing else has
been sent for `heartbeat_s`, so proxies and the browser keep the connection open while the
model or a tool is slow. `EventStreamResponse` makes sure the event source is closed however
the response ends (finished, client gone, or cancelled), so the producer's cleanup (saving a
partial answer, releasing the stream slot) always runs.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Final

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Send

from cardwise_api.stream_events import StreamEvent, stream_event_adapter

HEARTBEAT: Final = b": keep-alive\n\n"

SSE_HEADERS: Final = {
    "Cache-Control": "no-cache, no-store",
    "X-Accel-Buffering": "no",
}


def encode_event(event: StreamEvent) -> bytes:
    """One `data:` line per event. JSON never contains a raw newline, so one line is enough."""
    return b"data: " + stream_event_adapter.dump_json(event) + b"\n\n"


async def sse_body(events: AsyncIterator[StreamEvent], heartbeat_s: float) -> AsyncIterator[bytes]:
    pending: asyncio.Task[StreamEvent] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(anext(events))
            done, _ = await asyncio.wait({pending}, timeout=heartbeat_s)
            if not done:
                yield HEARTBEAT
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            finally:
                pending = None
            yield encode_event(event)
    finally:
        # Shielded: when the client disconnects this runs inside a cancelled scope, and the
        # producer must still get to finish its cleanup.
        with anyio.CancelScope(shield=True):
            if pending is not None and not pending.done():
                pending.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await pending
            await _aclose(events)


async def _aclose(iterator: object) -> None:
    aclose = getattr(iterator, "aclose", None)
    if aclose is not None:
        await aclose()


class EventStreamResponse(StreamingResponse):
    media_type = "text/event-stream"

    def __init__(self, events: AsyncIterator[StreamEvent], *, heartbeat_s: float) -> None:
        super().__init__(sse_body(events, heartbeat_s), headers=SSE_HEADERS)

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            # On ASGI 2.4 servers a gone client surfaces as OSError from `send`, which leaves
            # the generator suspended; close it now instead of at garbage collection.
            with anyio.CancelScope(shield=True):
                await _aclose(self.body_iterator)
