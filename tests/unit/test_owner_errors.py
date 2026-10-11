import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException

from src.api.owner.errors import OwnerApiError, OwnerRoute


def app_with_failing_routes(log: list[str]) -> FastAPI:
    async def transaction():
        try:
            yield
        except Exception as exc:
            log.append(f"rollback {type(exc).__name__}")
            raise
        log.append("commit")

    router = APIRouter(route_class=OwnerRoute, dependencies=[Depends(transaction)])

    @router.get("/field")
    async def field() -> None:
        raise OwnerApiError(422, {"field": "title", "message": "Назови вечер"})

    @router.get("/plain")
    async def plain() -> None:
        raise HTTPException(418, "short and stout")

    @router.get("/fine")
    async def fine() -> dict[str, bool]:
        return {"ok": True}

    app = FastAPI()
    app.include_router(router)
    return app


async def test_owner_error_body_is_top_level_and_transaction_rolls_back():
    log: list[str] = []
    transport = httpx.ASGITransport(app=app_with_failing_routes(log))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/field")
    assert response.status_code == 422
    assert response.json() == {"field": "title", "message": "Назови вечер"}
    assert log == ["rollback OwnerApiError"]  # the request transaction never commits on an error


async def test_other_errors_and_success_are_untouched():
    log: list[str] = []
    transport = httpx.ASGITransport(app=app_with_failing_routes(log))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        teapot = await client.get("/plain")
        fine = await client.get("/fine")
    assert teapot.status_code == 418
    assert teapot.json() == {"detail": "short and stout"}
    assert fine.json() == {"ok": True}
    assert log == ["rollback HTTPException", "commit"]


async def test_declared_body_over_the_limit_is_413_before_the_route_runs():
    log: list[str] = []
    transport = httpx.ASGITransport(app=app_with_failing_routes(log))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        over = await client.get("/fine", headers={"Content-Length": str(16 * 1024 * 1024 + 1)})
        exact = await client.get("/fine", headers={"Content-Length": str(16 * 1024 * 1024)})
        malformed = await client.get("/fine", headers={"Content-Length": "lots"})
    assert over.status_code == 413
    assert over.json() == {"message": "Файл больше 15 МБ"}
    assert exact.json() == {"ok": True}
    assert malformed.json() == {"ok": True}  # left to Starlette
    assert log == ["commit", "commit"]  # the rejected request never reached the dependencies
