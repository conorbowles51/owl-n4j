"""
Routers package - API endpoints.
"""

from routers.graph import router as graph_router
from routers.chat import router as chat_router
from routers.query import router as query_router
from routers.timeline import router as timeline_router
from routers.snapshots import router as snapshots_router
from routers.cases import router as cases_router
from routers.auth import router as auth_router
from routers.evidence import router as evidence_router
from routers.background_tasks import router as background_tasks_router

__all__ = [
    "graph_router",
    "chat_router",
    "query_router",
    "timeline_router",
    "snapshots_router",
    "cases_router",
    "auth_router",
    "evidence_router",
    "background_tasks_router",
]
