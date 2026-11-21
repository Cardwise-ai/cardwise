"""Response headers for an API that only ever serves JSON and event streams to its own web app."""

from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_ALWAYS: Final[tuple[tuple[bytes, bytes], ...]] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
)
_HSTS: Final = (b"strict-transport-security", b"max-age=63072000; includeSubDomains")
_NO_STORE: Final = (b"cache-control", b"no-store")


class SecurityHeadersMiddleware:
    """Adds the headers to every HTTP response, streams included.

    Nothing the API returns is cacheable: chat data is per user and errors carry request IDs,
    so `Cache-Control: no-store` is set unless a route chose its own. HSTS is sent when the
    request arrived over https or the app runs on a deployed (always-https) environment.
    """

    def __init__(self, app: ASGIApp, *, force_hsts: bool = False) -> None:
        self.app = app
        self.force_hsts = force_hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        hsts = self.force_hsts or scope.get("scheme") == "https"

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                extra = [*_ALWAYS, _NO_STORE] + ([_HSTS] if hsts else [])
                headers.extend(h for h in extra if h[0] not in present)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
