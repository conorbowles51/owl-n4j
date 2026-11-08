"""
Loupe - FastAPI Backend

Main entry point for the API server.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import (
    API_HOST,
    API_PORT,
    CORS_ORIGINS,
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
    case_exports_router,
    dossiers_router,
    auth_router,
    evidence_router,
    background_tasks_router,
    profiles_router,
    filesystem_router,
    chat_history_router,
    system_logs_router,
    removed_records_router,
    backfill_router,
    database_router,
    llm_config_router,
    ai_settings_router,
    workspace_router,
    work_router,
    workspace_overview_router,
    workspace_entries_router,
    workspace_ai_router,
    agent_proposals_router,
    phone_monitoring_router,
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
from services import process_shutdown


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    from services.startup_secrets_warning import warn_when_not_enforced
    warn_when_not_enforced()
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
    # Phone links (phone_extraction, phone_file) are checked against the capture tables (07 section 6).
    from services.phone import resolvers as phone_resolvers
    phone_resolvers.register()
    from services.pattern_of_life import evaluation as pol_evaluation
    pol_evaluation.register()  # statement_check links (04 section 9.6)
    from services.pattern_of_life import snapshots as pol_snapshots
    pol_snapshots.register()  # phone_analysis links: frozen pattern results (07 section 6.4 item 13)
    from services.phone import external_processing as phone_external_processing
    phone_external_processing.install()  # phone files as evidence: processed only when their report allows it
    # Phone mappings (02 section 6): the sweep re-derives when the loaded set changes.
    from services.phone import mappings as phone_mappings
    phone_mappings.install()
    from services.phone import identities as phone_identities
    phone_identities.install()  # after the mappings: identities read the comm events
    from services.phone import readings as phone_readings
    phone_readings.install()  # reading, region and owner decisions; the decision revision
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

    # Closing abandoned ingestion runs and the payment-category sweep are host-wide: they run once per host in the
    # batch-rounds child (services.financial.batch_rounds.HOST_SWEEPS), started by run_batches_forever below.

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

    # Address lookups for cases whose lookup is automatic: one worker per host does them (services.address_lookup).
    from services.address_lookup import run_auto_lookups_forever
    address_lookup_task = asyncio.create_task(run_auto_lookups_forever(), name="address-lookups")

    # Phone interpretation (docs/cellebrite/02 sections 1.3 and 5.7) runs in a process of its own, one per box,
    # supervised from here and stopped with the backend.
    from services.phone.sweep_worker import supervise_forever as run_phone_interpretation_forever
    phone_interpretation_task = asyncio.create_task(run_phone_interpretation_forever(), name="phone-interpretation")

    from services.financial.deployment_recovery import run_recovery_forever
    recovery_task = asyncio.create_task(run_recovery_forever(), name="financial-deployment-recovery")

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

    # Deleted items older than 30 days are purged with the delete used before (services/casebin_purge.py); one
    # process at a time across the host (advisory lock).
    from services.casebin_purge import run_purge_forever
    casebin_purge_task = asyncio.create_task(run_purge_forever(), name="deleted-items-purge")

    # A meaning-search gap backfill a restart ended resumes without waiting for someone to search (services.meaning_search).
    from services.meaning_search import resume_backfill_forever
    backfill_resume_task = asyncio.create_task(resume_backfill_forever(), name="meaning-search-backfill-resume")

    # An agent run killed by a restart is marked interrupted, never left running (services.agent.run_settle).
    from services.agent.run_settle import settle_forever as settle_agent_runs_forever
    agent_run_settle_task = asyncio.create_task(settle_agent_runs_forever(), name="agent-run-settle")

    # New evidence is scanned for malware in the background; the task ends at once while its switch is off.
    from services.evidence_file_check import resolve_stored_path as _resolve_evidence_path
    from services.evidence_malware import run_scans_forever
    from config import EVIDENCE_DATA_ROOT as _evidence_root
    malware_scan_task = asyncio.create_task(run_scans_forever(lambda path: _resolve_evidence_path(path, _evidence_root)),
                                            name="evidence-malware-scan")
    # Whole-case exports: each runs as a process of its own; this starts them, watches them and removes old packages.
    from services.caseport.jobs import run_forever as run_case_exports_forever
    case_exports_task = asyncio.create_task(run_case_exports_forever(), name="case-exports")

    # Jobs the old backend started after this one's start are recovered once it has stopped (services.backend_handover).
    from services.backend_handover import after_old_backend_stopped
    handover_task = asyncio.create_task(after_old_backend_stopped(job_subscriber.recover_after_handover),
                                        name="backend-handover-recovery")

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
        [recovery_task, identity_graph_task, address_lookup_task, phone_interpretation_task, financial_batches_task,
         view_warmup_task, view_refresh_task, case_files_task, cleanup_task, platform_update_task, loop_lag_task,
         casebin_purge_task, malware_scan_task, case_exports_task, handover_task, agent_run_settle_task, backfill_resume_task],
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

# A 422 reply never echoes submitted values, such as a password sent under a wrong field name.
from services.validation_reply import install as _validation_reply_without_input
_validation_reply_without_input(app)

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
# HSTS, only on a site served over HTTPS (LOUPE_HTTPS).
from services.https_headers import install as _strict_transport_on_https
_strict_transport_on_https(app)
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
app.include_router(case_exports_router)
app.include_router(dossiers_router)
app.include_router(auth_router)
app.include_router(evidence_router)
from routers.transcripts import router as transcripts_router
app.include_router(transcripts_router)
from routers.evidence_uploads import router as evidence_uploads_router
app.include_router(evidence_uploads_router)
from routers.evidence_upload_groups import router as evidence_upload_groups_router
app.include_router(evidence_upload_groups_router)
app.include_router(background_tasks_router)
app.include_router(profiles_router)
app.include_router(filesystem_router)
app.include_router(chat_history_router)
app.include_router(system_logs_router)
app.include_router(removed_records_router)
app.include_router(backfill_router)
app.include_router(database_router)
app.include_router(llm_config_router)
app.include_router(ai_settings_router)
app.include_router(work_router)
app.include_router(workspace_overview_router)
app.include_router(workspace_router)
app.include_router(workspace_entries_router)
app.include_router(workspace_ai_router)
app.include_router(agent_proposals_router)
app.include_router(phone_monitoring_router)
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
app.include_router(triage_router)
app.include_router(significant_router)
app.include_router(evidence_ws_router)
from routers.activity import router as activity_router
app.include_router(activity_router)
from routers.request_speed import router as request_speed_router
app.include_router(request_speed_router)
from routers.ui_problem_reports import router as ui_problem_reports_router
app.include_router(ui_problem_reports_router)
from routers.phone_extractions import router as phone_extractions_router
app.include_router(phone_extractions_router)
from routers.phones import router as phones_router
app.include_router(phones_router)
from routers.phone_analysis import router as phone_analysis_router
app.include_router(phone_analysis_router)
from routers.case_briefs import router as case_briefs_router
app.include_router(case_briefs_router)
from routers.search import router as search_router
app.include_router(search_router)
from routers.citations import router as citations_router
app.include_router(citations_router)
from routers.pattern_of_life import router as pattern_of_life_router
app.include_router(pattern_of_life_router)
from services.pattern_of_life import places as _pol_places
_pol_places.check_reverse_geocoding_at_startup()  # 04 section 6.5: only an in-house backend, else off and logged


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
        "process": _process_identity(),
    }


def _started_commit():
    from services.runtime_version import started_commit
    return started_commit()


def _process_identity():
    from services.backend_handover import process_identity
    return process_identity()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
    )
