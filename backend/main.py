"""
Investigation Console - FastAPI Backend

Main entry point for the API server.
"""

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import API_HOST, API_PORT, CORS_ORIGINS
from routers import (
    graph_router,
    chat_router,
    query_router,
    timeline_router,
    snapshots_router,
    cases_router,
    case_members_router,
    auth_router,
    evidence_router,
    background_tasks_router,
    profiles_router,
    filesystem_router,
    chat_history_router,
    system_logs_router,
    backfill_router,
    database_router,
    llm_config_router,
    workspace_router,
    users_router,
    setup_router,
    cost_ledger_router,
    financial_router,
    maintenance_router,
    case_deadlines_router,
    cellebrite_router,
)
from services.neo4j_service import neo4j_service
from services.snapshot_storage import snapshot_storage
from routers.snapshots import _cleanup_stale_chunks


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    print("Starting Investigation Console API...")
    try:
        # Reload snapshots from disk (non-blocking)
        snapshot_storage.reload()
        print(f"Loaded {len(snapshot_storage.get_all())} snapshots from storage")
    except Exception as e:
        print(f"Warning: Failed to load snapshots: {e}")

    # Cases are now stored in PostgreSQL - no JSON file to reload

    # Background task: clean up orphaned chunk upload cache entries
    cleanup_task = asyncio.create_task(_cleanup_stale_chunks())

    yield

    cleanup_task.cancel()
    # Shutdown
    print("Shutting down, closing Neo4j connection...")
    try:
        neo4j_service.close()
    except Exception as e:
        print(f"Warning: Error closing Neo4j connection: {e}")


app = FastAPI(
    title="Investigation Console API",
    description="API for fraud investigation graph visualization and AI-powered queries",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(graph_router)
app.include_router(chat_router)
app.include_router(query_router)
app.include_router(timeline_router)
app.include_router(snapshots_router)
app.include_router(cases_router)
app.include_router(case_members_router)
app.include_router(auth_router)
app.include_router(evidence_router)
app.include_router(background_tasks_router)
app.include_router(profiles_router)
app.include_router(filesystem_router)
app.include_router(chat_history_router)
app.include_router(system_logs_router)
app.include_router(backfill_router)
app.include_router(database_router)
app.include_router(llm_config_router)
app.include_router(workspace_router)
app.include_router(users_router)
app.include_router(setup_router)
app.include_router(cost_ledger_router)
app.include_router(financial_router)
app.include_router(maintenance_router)
app.include_router(case_deadlines_router)
app.include_router(cellebrite_router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Investigation Console API",
        "version": "1.0.0",
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    try:
        # Test Neo4j connection with a lightweight query
        neo4j_service._driver.verify_connectivity()
        neo4j_status = "connected"
    except Exception as e:
        neo4j_status = f"error: {str(e)}"

    return {
        "status": "ok",
        "neo4j": neo4j_status,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
    )
