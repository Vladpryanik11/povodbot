from src.api.owner import (  # noqa: F401  (register their routes on the router)
    campaigns,
    events,
    posters,
)
from src.api.owner.router import router

__all__ = ["router"]
