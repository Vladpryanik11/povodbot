from fastapi import APIRouter

from src.core.observability import snapshot_metrics

router = APIRouter(tags=["observability"])


@router.get("/metrics")
async def metrics() -> dict[str, int]:
    return snapshot_metrics()
