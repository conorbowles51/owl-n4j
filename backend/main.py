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
    triage_router,
    case_entities_router,
    testing_router,
    docket_router,
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

    # Watchdog: any cellebrite_ingestion (or upload) task left in
    # pending/running state by a previous backend instance that died
    # mid-flight is now genuinely dead — the worker thread didn't
    # survive the restart. Surface them as FAILED so the UI doesn't
    # show "running forever" and so the advisory lock doesn't block
    # legitimate retries. Threshold = 5 min of no heartbeat (the
    # ingest heartbeats every ~2s during the write loop).
    try:
        from datetime import timedelta
        from services.background_task_storage import background_task_storage, TaskStatus
        from services._timeutil import utcnow, utcnow_iso, parse_iso_utc

        # Aware UTC now + tolerant parser: task timestamps may be offset-aware
        # (new rows via utcnow_iso) or naive (legacy rows). parse_iso_utc
        # coerces both to aware UTC so this subtraction never raises the
        # "can't subtract offset-naive and offset-aware datetimes" TypeError.
        now = utcnow()
        stale_threshold = timedelta(minutes=5)
        rescued = 0
        for status_filter in (TaskStatus.RUNNING.value, TaskStatus.PENDING.value):
            for t in background_task_storage.list_tasks(status=status_filter, limit=500):
                if t.get("task_type") not in ("cellebrite_ingestion", "file_upload"):
                    continue
                ts = (t.get("updated_at") or t.get("started_at")
                      or t.get("created_at"))
                ts_dt = parse_iso_utc(ts)
                # If we can't read the timestamp, treat as stale —
                # safer than leaving an undead task blocking retries.
                if ts_dt is None or (now - ts_dt) > stale_threshold:
                    background_task_storage.update_task(
                        t["id"],
                        status=TaskStatus.FAILED.value,
                        completed_at=utcnow_iso(),
                        error=("process died mid-ingest (backend restarted) — "
                               "last heartbeat was "
                               f"{(now - ts_dt) if ts_dt else 'unknown'} ago"),
                    )
                    rescued += 1
        if rescued:
            print(f"Watchdog: marked {rescued} stale task(s) as failed")
    except Exception as e:
        print(f"Warning: stalled-task watchdog failed: {e}")

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
app.include_router(triage_router)
# QA testing hub: serves /testing + /api/testing/* (checklist + feedback).
app.include_router(testing_router)
# Docket: the ticket pipeline API at /api/tickets/* (lifecycle + queue + board).
app.include_router(docket_router)
# Investigator-curated dossier profiles. Mounted at both URLs:
#   /api/case-profiles  — new canonical route (frontend uses this)
#   /api/entities       — legacy alias (kept for back-compat)
app.include_router(case_entities_router, prefix="/api/case-profiles")
app.include_router(case_entities_router, prefix="/api/entities")

# Docket standalone UI (built React app) served at /docket. The bundle is
# produced by `npm run build` in docket/ during deploy; mount only if present so
# the backend still boots in environments where the UI hasn't been built.
from pathlib import Path as _Path  # noqa: E402
from fastapi.staticfiles import StaticFiles as _StaticFiles  # noqa: E402

_DOCKET_DIST = _Path(__file__).resolve().parent.parent / "docket" / "dist"
if _DOCKET_DIST.is_dir():
    app.mount("/docket", _StaticFiles(directory=str(_DOCKET_DIST), html=True), name="docket")
    print(f"[Docket] UI mounted at /docket from {_DOCKET_DIST}")
else:
    print("[Docket] UI bundle not found at docket/dist — run `npm run build` in docket/ to enable /docket")


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
