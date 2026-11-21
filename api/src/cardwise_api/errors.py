"""Request IDs and the single error shape. Responses never include stack traces or internals."""

import uuid
from typing import Final, cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from cardwise_api.models import ErrorBody, ErrorCode, ErrorDetail

REQUEST_ID_HEADER: Final = "x-request-id"

_STATUS_CODES: Final[dict[int, ErrorCode]] = {
    400: "bad_request",
    401: "unauthorized",
    404: "not_found",
    405: "bad_request",
    422: "bad_request",
    429: "rate_limited",
    501: "not_implemented",
}

_MESSAGES: Final[dict[ErrorCode, str]] = {
    "bad_request": "The request is not valid.",
    "unauthorized": "Sign in to continue.",
    "not_found": "Not found.",
    "rate_limited": "Too many requests. Try again later.",
    "not_implemented": "Not available yet.",
    "internal": "Something went wrong on our side.",
}


class RequestIdMiddleware:
    """Gives every request a fresh ID, echoed in the response header and error bodies.

    Plain ASGI rather than BaseHTTPMiddleware so streaming responses and client disconnects
    pass through untouched. Client-sent IDs are ignored to keep log correlation trustworthy.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_id)


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def error_response(
    request: Request, status: int, code: ErrorCode, fields: list[str] | None = None
) -> JSONResponse:
    body = ErrorBody(
        error=ErrorDetail(
            code=code,
            message=_MESSAGES[code],
            request_id=request_id(request),
            fields=fields or [],
        )
    )
    return JSONResponse(body.model_dump(mode="json"), status_code=status)


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(HTTPException, exc)
    code = _STATUS_CODES.get(exc.status_code, "internal")
    status = exc.status_code if exc.status_code in _STATUS_CODES else 500
    response = error_response(request, status, code)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(RequestValidationError, exc)
    fields = sorted({".".join(str(p) for p in err["loc"][1:]) for err in exc.errors()})
    return error_response(request, 422, "bad_request", fields)


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    return error_response(request, 500, "internal")


def install_error_handling(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)
