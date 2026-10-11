"""Owner API errors: the body is the error itself, not FastAPI's `{"detail": ...}` wrapper."""

from typing import Any

from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.datastructures import Headers
from starlette.types import Receive, Scope, Send

# A poster is at most 15 MB; the rest is room for the multipart framing and form fields.
MAX_BODY_BYTES = 16 * 1024 * 1024
BODY_TOO_LARGE = "Файл больше 15 МБ"


class OwnerApiError(Exception):
    def __init__(self, status_code: int, body: dict[str, str]):
        super().__init__(body.get("message", ""))
        self.status_code = status_code
        self.body = body


class OwnerRoute(APIRoute):
    """Turns `OwnerApiError` into its JSON body for the routes of one router only.

    The handler wraps the finished route app, outside the request's dependencies, so a
    transaction-per-request session rolls back first and the error body is built afterwards.

    It also turns away a request that declares a body over `MAX_BODY_BYTES` before the inner app
    parses the multipart body, which FastAPI would do ahead of authorization. A request without
    the header (chunked) is not caught here; that limit belongs to the reverse proxy.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        inner = self.app

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            if _declared_length(scope) > MAX_BODY_BYTES:
                response = JSONResponse({"message": BODY_TOO_LARGE}, status_code=413)
                await response(scope, receive, send)
                return
            try:
                await inner(scope, receive, send)
            except OwnerApiError as error:
                response = JSONResponse(error.body, status_code=error.status_code)
                await response(scope, receive, send)

        self.app = app


def _declared_length(scope: Scope) -> int:
    value = Headers(scope=scope).get("content-length")
    try:
        return int(value) if value is not None else 0
    except ValueError:
        return 0  # malformed: Starlette deals with it
