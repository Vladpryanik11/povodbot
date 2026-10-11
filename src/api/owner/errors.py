"""Owner API errors: the body is the error itself, not FastAPI's `{"detail": ...}` wrapper."""

from typing import Any

from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.types import Receive, Scope, Send


class OwnerApiError(Exception):
    def __init__(self, status_code: int, body: dict[str, str]):
        super().__init__(body.get("message", ""))
        self.status_code = status_code
        self.body = body


class OwnerRoute(APIRoute):
    """Turns `OwnerApiError` into its JSON body for the routes of one router only.

    The handler wraps the finished route app, outside the request's dependencies, so a
    transaction-per-request session rolls back first and the error body is built afterwards.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        inner = self.app

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            try:
                await inner(scope, receive, send)
            except OwnerApiError as error:
                response = JSONResponse(error.body, status_code=error.status_code)
                await response(scope, receive, send)

        self.app = app
