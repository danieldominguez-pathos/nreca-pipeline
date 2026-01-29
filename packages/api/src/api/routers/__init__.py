"""API routers."""

from api.routers.admin import router as admin_router
from api.routers.ingest import router as ingest_router
from api.routers.query import router as query_router

__all__ = ["admin_router", "ingest_router", "query_router"]
