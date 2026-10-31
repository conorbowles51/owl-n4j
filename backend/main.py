"""
Loupe - FastAPI Backend

Main entry point for the API server.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import (
    API_HOST,
    API_PORT,
    CORS_ORIGINS,
    FINANCIAL_RUN_REAP_INTERVAL_SECONDS,
    FINANCIAL_RUN_STALE_AFTER_HOURS,
)
from routers import (
    graph_router,
    chat_router,
    agent_router,
    query_router,
    timeline_router,
    snapshots_router,
    cases_router,
    case_members_router,
    dossiers_router,
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
    ai_settings_router,
    workspace_router,
    work_router,
    workspace_overview_router,
    workspace_entries_router,
    workspace_ai_router,
    users_router,
    setup_router,
    cost_ledger_router,
    admin_ai_costs_router,
    admin_reader_gaps_router,
    admin_party_coverage_router,
    admin_update_router,
    financial_router,
    financial_ledger_router,
    financial_statement_import_router,
    financial_ingest_router,
    financial_adjudication_router,
    financial_reconciliation_router,
    financial_judgements_router,
    maintenance_router,
    case_deadlines_router,
    notebook_router,
    evidence_folders_router,
    cellebrite_router,
    triage_router,
    significant_router,
)
from services.neo4j_service import neo4j_service
from services.snapshot_storage import snapshot_storage
from services import evidence_engine_client
from routers.snapshots import _cleanup_stale_chunks
from routers.evidence_ws import router as evidence_ws_router, close_redis
from services.job_status_subscriber import get_subscriber
from services.neo4j.driver import driver
from services.platform_update_service import platform_update_service
from services.financial.run_reaper import reap_stale_runs_forever
from services import process_shutdown


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    print("Starting Loupe API...")
    # The first SIGTERM/SIGINT marks the process as stopping and arms a
    # hard-deadline watchdog, so no task, thread or blocked loop can hold a
    # stop open for systemd's whole stop window.
    process_shutdown.install_signal_handlers()
    # kill -USR1 <worker> writes every thread's stack to the journal (services/thread_dump.py).
    from services import thread_dump
    thread_dump.install()
    # What this process runs, for /health (deploy records it as last good).
    from services.runtime_version import record_started_commit
    record_started_commit()
    try:
        # Reload snapshots from disk (non-blocking)
        snapshot_storage.reload()
        print(f"Loaded {len(snapshot_storage.get_all())} snapshots from storage")
    except Exception as e:
        print(f"Warning: Failed to load snapshots: {e}")

    # Cases are now stored in PostgreSQL - no JSON file to reload

    # Background task: clean up orphaned chunk upload cache entries
    cleanup_task = asyncio.create_task(_cleanup_stale_chunks(), name="upload-chunk-cleanup")
    platform_update_task = (
        asyncio.create_task(platform_update_service.poll_forever(), name="platform-update-poll")
        if platform_update_service.enabled
        else None
    )

    # Background task: close financial ingestion runs abandoned by a process
    # that was killed before it could record a terminal status. Nothing else
    # can close those: every in-process path already writes its own status, and
    # the case for this one is that there was no process left to run a handler.
    # Started here rather than exposed as an endpoint because the sweep is
    # global, not case-scoped, so behind a case-gated route a caller would be
    # terminating runs in cases they cannot see.
    run_reaper_task = asyncio.create_task(
        reap_stale_runs_forever(
            older_than=timedelta(hours=FINANCIAL_RUN_STALE_AFTER_HOURS),
            every=timedelta(seconds=FINANCIAL_RUN_REAP_INTERVAL_SECONDS),
        ),
        name="financial-run-reaper",
    )

    # Start Redis subscriber for evidence engine job status sync
    job_subscriber = get_subscriber()
    try:
        await job_subscriber.start()
    except Exception as e:
        print(f"Warning: Failed to start job status subscriber: {e}")

    from services.financial.import_batches import run_batches_forever
    financial_batches_task = asyncio.create_task(run_batches_forever(), name="financial-folder-batches")

    from services.financial.identity_graph import run_identity_graph_forever
    identity_graph_task = asyncio.create_task(run_identity_graph_forever(), name="financial-reviewed-identities")

    from services.financial.deployment_recovery import run_recovery_forever
    recovery_task = asyncio.create_task(run_recovery_forever(), name="financial-deployment-recovery")

    from services.financial.payment_categories import run_category_model_forever
    category_task = asyncio.create_task(run_category_model_forever(), name="financial-payment-categories")

    # How late this worker's event loop runs a 250 ms timer, max per minute (services.request_speed).
    from services.request_speed import run_loop_lag_probe
    loop_lag_task = asyncio.create_task(run_loop_lag_probe(), name="request-speed-loop-lag")

    # One worker computes each case's account history once after start (services.financial.view_warmup).
    from services.financial.view_warmup import warm_views_once
    view_warmup_task = asyncio.create_task(warm_views_once(), name="financial-view-warmup")
    # A changed slow view is computed again at once in one background process per host (services.financial.view_refresh).
    from services.financial.view_refresh import refresh_loop
    view_refresh_task = asyncio.create_task(refresh_loop(), name="financial-view-refresh")

    # Each worker loads the largest cases' evidence-file copies once (services.financial.view_warmup).
    from services.financial.view_warmup import warm_case_files_once
    case_files_task = asyncio.create_task(warm_case_files_once(), name="financial-case-files-warmup")

    # The application loaded so far lives as long as the process: keep it out
    # of every later garbage-collector pass (services.process_memory).
    from services.process_memory import freeze_startup_objects
    print(f"Startup objects excluded from garbage collection: {freeze_startup_objects()}")

    yield

    # Cancel the background loops and give in-flight atomic statement/graph
    # units a bounded time to finish before their clients close. A unit still
    # inside its worker thread after that is abandoned: its transaction rolls
    # back when the process ends, and its durable record (leased batch,
    # pending recovery item, revisioned graph sweep) resumes on the next start.
    await process_shutdown.stop_background_tasks(
        [recovery_task, identity_graph_task, financial_batches_task, category_task, view_warmup_task,
         view_refresh_task, case_files_task, cleanup_task, run_reaper_task, platform_update_task, loop_lag_task],
        timeout=process_shutdown.BACKGROUND_STOP_SECONDS,
    )

    # Save the request timings still queued in this worker (bounded; never blocks shutdown long).
    try:
        from services.request_speed import flush_now
        await asyncio.wait_for(asyncio.to_thread(flush_now), timeout=10)
    except Exception as e:
        print(f"Warning: request timings not saved at shutdown: {e}")

    # Stop job status subscriber
    try:
        await job_subscriber.stop()
    except Exception as e:
        print(f"Warning: Error stopping job status subscriber: {e}")
    # Shutdown
    print("Shutting down, closing connections...")
    try:
        neo4j_service.close()
    except Exception as e:
        print(f"Warning: Error closing Neo4j connection: {e}")
    try:
        await evidence_engine_client.close()
    except Exception as e:
        print(f"Warning: Error closing evidence engine client: {e}")
    try:
        await close_redis()
    except Exception as e:
        print(f"Warning: Error closing Redis connection: {e}")


# Route results are encoded in a worker thread, not on the event loop (services.response_encoding).
from services.response_encoding import install as _encode_off_the_loop
_encode_off_the_loop()

app = FastAPI(
    title="Loupe API",
    description="API for fraud investigation graph visualization and AI-powered queries",
    version="1.0.0",
    lifespan=lifespan,
)

# JSON responses are gzipped for browsers that accept it (services.json_gzip). Added first, so it is the
# innermost layer: the timing middlewares below record the bytes actually sent and the compression time.
from services.json_gzip import JSONGZipMiddleware
app.add_middleware(JSONGZipMiddleware)
# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Loupe-Case-Id", "X-Loupe-Account-Id",
        "X-Loupe-Start-Date", "X-Loupe-End-Date", "X-Loupe-PDF-Report",
        "X-Loupe-Source-Files", "X-Loupe-Table-View", "X-Loupe-Table-View-Sha256", "X-Loupe-Privilege-Marking",
        "X-Loupe-Case-Review-History", "X-Loupe-Archive-Sha256", "X-Loupe-Assembly-Inputs-Sha256", "X-Loupe-Scenario-Sha256",
        "X-Loupe-Export-Id", "X-Loupe-Export-Event-Sha256", "X-Loupe-Export-Event-Sequence",
        "X-Request-ID", "Server-Timing", "X-Financial-View-State", "X-Financial-View-As-Of"],
)
# Correlation id and per-stage Server-Timing on financial batch endpoints.
from services.financial.request_timing import FinancialTimingMiddleware
app.add_middleware(FinancialTimingMiddleware)
# A Financial page request that can show a view marked updating (services.financial.view_cache).
from services.financial.view_cache import AcceptsUpdatingMiddleware
app.add_middleware(AcceptsUpdatingMiddleware)
# How long every /api request takes, kept permanently (services.request_speed).
from services.request_speed import RequestSpeedMiddleware
app.add_middleware(RequestSpeedMiddleware)
# Source address, user agent and screen of every request, for the activity trail.
from services.activity_trail import ActivityContextMiddleware
app.add_middleware(ActivityContextMiddleware)

# Include routers
app.include_router(graph_router)
app.include_router(chat_router)
app.include_router(agent_router)
app.include_router(query_router)
app.include_router(timeline_router)
app.include_router(snapshots_router)
app.include_router(cases_router)
app.include_router(case_members_router)
app.include_router(dossiers_router)
app.include_router(auth_router)
app.include_router(evidence_router)
from routers.evidence_uploads import router as evidence_uploads_router
app.include_router(evidence_uploads_router)
from routers.evidence_upload_groups import router as evidence_upload_groups_router
app.include_router(evidence_upload_groups_router)
app.include_router(background_tasks_router)
app.include_router(profiles_router)
app.include_router(filesystem_router)
app.include_router(chat_history_router)
app.include_router(system_logs_router)
app.include_router(backfill_router)
app.include_router(database_router)
app.include_router(llm_config_router)
app.include_router(ai_settings_router)
app.include_router(work_router)
app.include_router(workspace_overview_router)
app.include_router(workspace_router)
app.include_router(workspace_entries_router)
app.include_router(workspace_ai_router)
app.include_router(users_router)
app.include_router(setup_router)
app.include_router(cost_ledger_router)
app.include_router(admin_ai_costs_router)
app.include_router(admin_reader_gaps_router)
app.include_router(admin_party_coverage_router)
app.include_router(admin_update_router)
app.include_router(financial_router)
app.include_router(financial_ledger_router)
app.include_router(financial_statement_import_router)
from routers.financial_source_audit import router as financial_source_audit_router
app.include_router(financial_source_audit_router)
app.include_router(financial_ingest_router)
app.include_router(financial_adjudication_router)
app.include_router(financial_reconciliation_router)
app.include_router(financial_judgements_router)
app.include_router(maintenance_router)
app.include_router(case_deadlines_router)
app.include_router(notebook_router)
app.include_router(evidence_folders_router)
app.include_router(cellebrite_router)
app.include_router(triage_router)
app.include_router(significant_router)
app.include_router(evidence_ws_router)
from routers.activity import router as activity_router
app.include_router(activity_router)
from routers.request_speed import router as request_speed_router
app.include_router(request_speed_router)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Loupe API",
        "version": "1.0.0",
    }


@app.get("/api/health")
async def api_health():
    """Liveness through the frontend's /api proxy, for the availability probe (scripts/host_recorder.py).
    No database or service call: it answers as soon as this worker's event loop runs it. It is public, so it says
    nothing else (the worker is in the Server-Timing header; the commit is on /health, which is not proxied)."""
    return {"status": "ok"}


@app.get("/health")
async def health():
    """Detailed health check."""
    try:
        # Keep health checks case-agnostic so deploys do not depend on a case-scoped API.
        with driver.session() as session:
            summary = session.run(
                """
                MATCH (n)
                RETURN count(n) AS total_nodes
                """
            ).single()
        neo4j_status = "connected"
        node_count = summary["total_nodes"] if summary else 0
    except Exception as e:
        neo4j_status = "error: unavailable"
        node_count = 0

    # Test evidence engine connection
    try:
        ee_health = await evidence_engine_client.health_check()
        evidence_engine_status = ee_health.get("status", "unknown")
    except Exception as e:
        evidence_engine_status = "error: unavailable"

    from starlette.concurrency import run_in_threadpool
    from services.runtime_readiness import database_readiness, overall_readiness
    database = await run_in_threadpool(database_readiness)
    return {
        "status": overall_readiness(neo4j_status, evidence_engine_status, database),
        "postgres": database['status'],
        "database_schema": database['schema'],
        "neo4j": neo4j_status,
        "nodes": node_count,
        "evidence_engine": evidence_engine_status,
        **_started_commit(),
    }


def _started_commit():
    from services.runtime_version import started_commit
    return started_commit()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
    )
