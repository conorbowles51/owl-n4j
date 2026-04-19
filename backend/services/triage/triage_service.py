"""
Triage Service

Main orchestrator for triage cases: CRUD, scan orchestration,
classification, profiling, custom stage execution.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from services.background_task_storage import background_task_storage, TaskStatus
from services.triage.triage_storage import triage_storage
from services.triage.scanner_service import triage_scanner
from services.triage.classifier_service import triage_classifier
from services.triage.hash_lookup_service import hash_lookup_service
from services.triage.profiler_service import triage_profiler
from services.triage.processor_registry import processor_registry
from services.triage.triage_advisor import triage_advisor
from services.triage.template_service import template_service
from services.triage.ingest_bridge import ingest_bridge

logger = logging.getLogger(__name__)


class TriageService:
    """Orchestrates triage cases and their processing stages."""

    def __init__(self):
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
        return self._driver

    # ── Case CRUD ──────────────────────────────────────────────────────

    def create_case(
        self,
        name: str,
        description: str,
        source_path: str,
        created_by: str,
    ) -> Dict:
        p = Path(source_path)
        if not p.exists():
            raise ValueError(f"Source path does not exist: {source_path}")
        if not p.is_dir():
            raise ValueError(f"Source path is not a directory: {source_path}")

        case = triage_storage.create_case(
            name=name,
            description=description,
            source_path=str(p.resolve()),
            created_by=created_by,
        )
        logger.info(f"Created triage case {case['id']}: {name}")
        return case

    def get_case(self, case_id: str) -> Optional[Dict]:
        return triage_storage.get_case(case_id)

    def list_cases(self, owner: Optional[str] = None) -> List[Dict]:
        return triage_storage.list_cases(owner=owner)

    def delete_case(self, case_id: str) -> bool:
        # Delete Neo4j nodes
        driver = self._get_driver()
        with driver.session() as session:
            session.run(
                "MATCH (n {triage_case_id: $id}) DETACH DELETE n",
                id=case_id,
            )
        # Delete JSON record
        deleted = triage_storage.delete_case(case_id)
        if deleted:
            logger.info(f"Deleted triage case {case_id}")
        return deleted

    # ── Scan (Stage 0) ────────────────────────────────────────────────

    def start_scan(self, case_id: str, resume: bool = False) -> str:
        """Start or resume a directory scan. Returns background task_id."""
        case = triage_storage.get_case(case_id)
        if not case:
            raise ValueError(f"Triage case not found: {case_id}")

        source_path = case["source_path"]
        if not Path(source_path).exists():
            raise ValueError(f"Source path no longer exists: {source_path}")

        scan_stage = None
        for s in case.get("stages", []):
            if s.get("type") == "scan":
                scan_stage = s
                break
        if not scan_stage:
            raise ValueError("No scan stage found in triage case")

        scan_cursor = case.get("scan_cursor") if resume else None

        # Create background task
        task = background_task_storage.create_task(
            task_type="triage_scan",
            task_name=f"Scanning: {case.get('name', case_id)}",
            owner=case.get("created_by"),
            case_id=case_id,
            metadata={"triage_case_id": case_id, "source_path": source_path},
        )
        task_id = task["id"]

        # Update case and stage status
        triage_storage.update_case(case_id, status="scanning")
        triage_storage.update_stage(
            case_id,
            scan_stage["id"],
            status="running",
            started_at=datetime.now().isoformat(),
        )

        def _run_scan():
            try:
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.RUNNING.value,
                    started_at=datetime.now().isoformat(),
                )

                def _log(msg):
                    logger.info(f"[triage:{case_id[:8]}] {msg}")

                def _progress(scanned, _est):
                    background_task_storage.update_task(
                        task_id,
                        progress_completed=scanned,
                    )
                    # Persist cursor periodically
                    triage_storage.update_stage(
                        case_id,
                        scan_stage["id"],
                        files_processed=scanned,
                    )

                result = triage_scanner.scan(
                    triage_case_id=case_id,
                    source_path=source_path,
                    scan_cursor=scan_cursor,
                    log_callback=_log,
                    progress_callback=_progress,
                )

                # Update case with results
                triage_storage.update_case(
                    case_id,
                    status="scan_complete",
                    scan_cursor=result.get("last_cursor"),
                    scan_stats={
                        "total_files": result["total_files"],
                        "total_size": result["total_size"],
                        "os_detected": result.get("os_detected"),
                        "by_category": result.get("by_category", {}),
                        "by_category_size": result.get("by_category_size", {}),
                        "extension_mismatches": result.get("extension_mismatches", 0),
                        "unique_hashes": result.get("unique_hashes", 0),
                    },
                )
                triage_storage.update_stage(
                    case_id,
                    scan_stage["id"],
                    status="completed",
                    completed_at=datetime.now().isoformat(),
                    files_total=result["total_files"],
                    files_processed=result["total_files"],
                )

                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED.value,
                    completed_at=datetime.now().isoformat(),
                    progress_total=result["total_files"],
                    progress_completed=result["total_files"],
                )

            except Exception as e:
                logger.exception(f"Scan failed for triage case {case_id}")
                triage_storage.update_case(case_id, status="scan_complete")
                triage_storage.update_stage(
                    case_id, scan_stage["id"],
                    status="failed",
                    error=str(e),
                )
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.FAILED.value,
                    error=str(e),
                    completed_at=datetime.now().isoformat(),
                )

        thread = threading.Thread(
            target=_run_scan,
            daemon=False,
            name=f"triage-scan-{case_id[:8]}",
        )
        thread.start()
        return task_id

    # ── Classification (Stage 1) ───────────────────────────────────────

    def start_classification(self, case_id: str) -> str:
        """Start file classification. Returns background task_id."""
        case = triage_storage.get_case(case_id)
        if not case:
            raise ValueError(f"Triage case not found: {case_id}")

        # Find classify stage
        classify_stage = None
        for s in case.get("stages", []):
            if s.get("type") == "classify":
                classify_stage = s
                break
        if not classify_stage:
            raise ValueError("No classify stage found in triage case")

        # Ensure scan is complete
        scan_stage = next(
            (s for s in case.get("stages", []) if s.get("type") == "scan"), None
        )
        if not scan_stage or scan_stage.get("status") != "completed":
            raise ValueError("Scan must be completed before classification")

        os_detected = case.get("scan_stats", {}).get("os_detected")

        # Create background task
        task = background_task_storage.create_task(
            task_type="triage_classify",
            task_name=f"Classifying: {case.get('name', case_id)}",
            owner=case.get("created_by"),
            case_id=case_id,
            metadata={"triage_case_id": case_id},
        )
        task_id = task["id"]

        # Update status
        triage_storage.update_case(case_id, status="classifying")
        triage_storage.update_stage(
            case_id,
            classify_stage["id"],
            status="running",
            started_at=datetime.now().isoformat(),
        )

        def _run_classification():
            try:
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.RUNNING.value,
                    started_at=datetime.now().isoformat(),
                )

                def _log(msg):
                    logger.info(f"[triage-classify:{case_id[:8]}] {msg}")

                def _progress(step, completed, total):
                    background_task_storage.update_task(
                        task_id,
                        progress_completed=completed,
                        progress_total=total,
                        metadata={"step": step},
                    )

                result = triage_classifier.classify(
                    triage_case_id=case_id,
                    os_detected=os_detected,
                    log_callback=_log,
                    progress_callback=_progress,
                )

                # Update case
                triage_storage.update_case(case_id, status="classified")
                triage_storage.update_stage(
                    case_id,
                    classify_stage["id"],
                    status="completed",
                    completed_at=datetime.now().isoformat(),
                    files_total=result.get("total_unique_hashes", 0),
                    files_processed=result.get("total_unique_hashes", 0),
                )

                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED.value,
                    completed_at=datetime.now().isoformat(),
                )

            except Exception as e:
                logger.exception(f"Classification failed for triage case {case_id}")
                triage_storage.update_case(case_id, status="scan_complete")
                triage_storage.update_stage(
                    case_id,
                    classify_stage["id"],
                    status="failed",
                    error=str(e),
                )
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.FAILED.value,
                    error=str(e),
                    completed_at=datetime.now().isoformat(),
                )

        thread = threading.Thread(
            target=_run_classification,
            daemon=False,
            name=f"triage-classify-{case_id[:8]}",
        )
        thread.start()
        return task_id

    def get_classification_stats(self, case_id: str) -> Dict:
        """Get classification statistics from Neo4j."""
        return triage_classifier.get_classification_stats(case_id)

    def upload_hash_set(self, name: str, hashes: List[str]) -> int:
        """Upload a custom hash set. Returns number of valid hashes."""
        return hash_lookup_service.add_custom_hash_set(name, hashes)

    def list_hash_sets(self) -> List[Dict]:
        """List available custom hash sets."""
        return hash_lookup_service.list_custom_sets()

    # ── Profiling (Stage 2) ──────────────────────────────────────────

    def generate_profile(self, case_id: str) -> str:
        """Generate triage profile/dashboard. Returns background task_id."""
        case = triage_storage.get_case(case_id)
        if not case:
            raise ValueError(f"Triage case not found: {case_id}")

        profile_stage = None
        for s in case.get("stages", []):
            if s.get("type") == "profile":
                profile_stage = s
                break
        if not profile_stage:
            raise ValueError("No profile stage found in triage case")

        # Classification should be complete (or at least scan)
        classify_stage = next(
            (s for s in case.get("stages", []) if s.get("type") == "classify"), None
        )
        scan_stage = next(
            (s for s in case.get("stages", []) if s.get("type") == "scan"), None
        )
        if not scan_stage or scan_stage.get("status") != "completed":
            raise ValueError("Scan must be completed before profiling")

        os_detected = case.get("scan_stats", {}).get("os_detected")

        task = background_task_storage.create_task(
            task_type="triage_profile",
            task_name=f"Profiling: {case.get('name', case_id)}",
            owner=case.get("created_by"),
            case_id=case_id,
            metadata={"triage_case_id": case_id},
        )
        task_id = task["id"]

        triage_storage.update_case(case_id, status="profiling")
        triage_storage.update_stage(
            case_id,
            profile_stage["id"],
            status="running",
            started_at=datetime.now().isoformat(),
        )

        def _run_profile():
            try:
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.RUNNING.value,
                    started_at=datetime.now().isoformat(),
                )

                def _log(msg):
                    logger.info(f"[triage-profile:{case_id[:8]}] {msg}")

                def _progress(step, completed, total):
                    background_task_storage.update_task(
                        task_id,
                        progress_completed=completed,
                        progress_total=total,
                        metadata={"step": step},
                    )

                result = triage_profiler.generate_profile(
                    triage_case_id=case_id,
                    os_detected=os_detected,
                    log_callback=_log,
                    progress_callback=_progress,
                )

                # Store profile in case data
                triage_storage.update_case(case_id, status="profiled", profile=result)
                triage_storage.update_stage(
                    case_id,
                    profile_stage["id"],
                    status="completed",
                    completed_at=datetime.now().isoformat(),
                )

                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED.value,
                    completed_at=datetime.now().isoformat(),
                )

            except Exception as e:
                logger.exception(f"Profiling failed for triage case {case_id}")
                triage_storage.update_case(case_id, status="classified")
                triage_storage.update_stage(
                    case_id,
                    profile_stage["id"],
                    status="failed",
                    error=str(e),
                )
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.FAILED.value,
                    error=str(e),
                    completed_at=datetime.now().isoformat(),
                )

        thread = threading.Thread(
            target=_run_profile,
            daemon=False,
            name=f"triage-profile-{case_id[:8]}",
        )
        thread.start()
        return task_id

    def get_profile(self, case_id: str) -> Optional[Dict]:
        """Get stored profile data."""
        case = triage_storage.get_case(case_id)
        if not case:
            return None
        return case.get("profile")

    def get_timeline(self, case_id: str) -> List[Dict]:
        """Get activity timeline from Neo4j."""
        return triage_profiler.get_timeline(case_id)

    def get_artifacts(self, case_id: str) -> List[Dict]:
        """Get detected high-value artifacts."""
        return triage_profiler.get_artifacts(case_id)

    def get_mismatches(self, case_id: str) -> List[Dict]:
        """Get extension mismatch files."""
        return triage_profiler.get_mismatches(case_id)

    # ── Custom Stages (Phase 4) ──────────────────────────────────────

    def list_processors(self) -> List[Dict]:
        """List available processors."""
        return processor_registry.list_processors()

    def create_custom_stage(
        self, case_id: str, name: str, processor_name: str,
        config: Dict, file_filter: Dict,
    ) -> Dict:
        """Create a custom processing stage."""
        case = triage_storage.get_case(case_id)
        if not case:
            raise ValueError(f"Triage case not found: {case_id}")

        # Validate processor exists
        proc = processor_registry.get_processor(processor_name)
        if not proc:
            raise ValueError(f"Unknown processor: {processor_name}")

        stage = triage_storage.add_stage(
            case_id,
            name=name,
            stage_type="custom",
            config={"processor_name": processor_name, "config": config, "file_filter": file_filter},
        )
        return stage

    def execute_stage(self, case_id: str, stage_id: str, max_workers: int = 4) -> str:
        """Execute a custom stage. Returns background task_id."""
        case = triage_storage.get_case(case_id)
        if not case:
            raise ValueError(f"Triage case not found: {case_id}")

        stage = None
        for s in case.get("stages", []):
            if s.get("id") == stage_id:
                stage = s
                break
        if not stage:
            raise ValueError(f"Stage not found: {stage_id}")
        if stage.get("type") != "custom":
            raise ValueError("Can only execute custom stages")

        stage_config = stage.get("config", {})
        processor_name = stage_config.get("processor_name")
        proc_config = stage_config.get("config", {})
        file_filter = stage_config.get("file_filter", {})

        task = background_task_storage.create_task(
            task_type="triage_process",
            task_name=f"Processing: {stage.get('name', stage_id)}",
            owner=case.get("created_by"),
            case_id=case_id,
            metadata={"triage_case_id": case_id, "stage_id": stage_id},
        )
        task_id = task["id"]

        triage_storage.update_case(case_id, status="processing")
        triage_storage.update_stage(
            case_id, stage_id,
            status="running",
            started_at=datetime.now().isoformat(),
        )

        def _run_stage():
            try:
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.RUNNING.value,
                    started_at=datetime.now().isoformat(),
                )

                def _log(msg):
                    logger.info(f"[triage-process:{case_id[:8]}:{stage_id[:8]}] {msg}")

                def _progress(completed, total):
                    background_task_storage.update_task(
                        task_id,
                        progress_completed=completed,
                        progress_total=total,
                    )
                    triage_storage.update_stage(
                        case_id, stage_id,
                        files_processed=completed,
                        files_total=total,
                    )

                result = processor_registry.execute_stage(
                    triage_case_id=case_id,
                    stage_id=stage_id,
                    processor_name=processor_name,
                    config=proc_config,
                    file_filter=file_filter,
                    max_workers=max_workers,
                    log_callback=_log,
                    progress_callback=_progress,
                )

                triage_storage.update_stage(
                    case_id, stage_id,
                    status="completed",
                    completed_at=datetime.now().isoformat(),
                    files_total=result["total_files"],
                    files_processed=result["total_files"],
                )

                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED.value,
                    completed_at=datetime.now().isoformat(),
                    progress_total=result["total_files"],
                    progress_completed=result["total_files"],
                )

            except Exception as e:
                logger.exception(f"Stage execution failed: {stage_id}")
                triage_storage.update_stage(
                    case_id, stage_id,
                    status="failed",
                    error=str(e),
                )
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.FAILED.value,
                    error=str(e),
                    completed_at=datetime.now().isoformat(),
                )

        thread = threading.Thread(
            target=_run_stage,
            daemon=False,
            name=f"triage-process-{stage_id[:8]}",
        )
        thread.start()
        return task_id

    def get_stage_results(self, case_id: str, stage_id: str) -> List[Dict]:
        """Get artifacts produced by a stage."""
        return processor_registry.get_stage_results(case_id, stage_id)

    def get_file_provenance(self, case_id: str, file_path: str) -> Dict:
        """Get provenance chain for a file."""
        return processor_registry.get_file_provenance(case_id, file_path)

    def get_file_artifacts(self, case_id: str, file_path: str) -> List[Dict]:
        """Get all artifacts for a specific file."""
        prov = processor_registry.get_file_provenance(case_id, file_path)
        return prov.get("artifacts", [])

    # ── Advisor (Phase 5) ────────────────────────────────────────────

    def advisor_chat(
        self, case_id: str, question: str,
        model_provider: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict:
        """Ask the triage advisor a question."""
        return triage_advisor.advise(
            case_id, question,
            model_provider=model_provider,
            model_id=model_id,
        )

    def advisor_suggest(self, case_id: str) -> List[Dict]:
        """Get auto-suggested next steps."""
        return triage_advisor.suggest_next_steps(case_id)

    # ── Templates (Phase 5) ──────────────────────────────────────────

    def save_template(
        self, case_id: str, name: str, description: str = "", created_by: str = "",
    ) -> Dict:
        """Save current case's custom stages as a template."""
        return template_service.save_template(case_id, name, description, created_by)

    def list_templates(self) -> List[Dict]:
        """List all workflow templates."""
        return template_service.list_templates()

    def get_template(self, template_id: str) -> Optional[Dict]:
        """Get a template by ID."""
        return template_service.get_template(template_id)

    def apply_template(self, template_id: str, case_id: str) -> List[Dict]:
        """Apply a template's stages to a case."""
        return template_service.apply_template(template_id, case_id)

    def delete_template(self, template_id: str) -> bool:
        """Delete a template."""
        return template_service.delete_template(template_id)

    # ── Ingestion Bridge (Phase 6) ───────────────────────────────────

    def ingest_preview(
        self, case_id: str, target_case_id: str,
        file_ids: List[str] = None,
        file_filter: Optional[Dict] = None,
        include_artifacts: bool = True,
    ) -> Dict:
        """Preview what would be ingested."""
        return ingest_bridge.preview(
            case_id,
            file_ids=file_ids,
            file_filter=file_filter,
            include_artifacts=include_artifacts,
        )

    def ingest_to_case(
        self, case_id: str, target_case_id: str,
        file_ids: List[str] = None,
        file_filter: Optional[Dict] = None,
        include_artifacts: bool = True,
        owner: str = "",
    ) -> str:
        """Ingest triage files into an Owl case. Returns background task_id."""
        case = triage_storage.get_case(case_id)
        if not case:
            raise ValueError(f"Triage case not found: {case_id}")

        task = background_task_storage.create_task(
            task_type="triage_ingest",
            task_name=f"Ingesting to case: {target_case_id[:8]}",
            owner=owner,
            case_id=case_id,
            metadata={
                "triage_case_id": case_id,
                "target_case_id": target_case_id,
            },
        )
        task_id = task["id"]

        def _run_ingest():
            try:
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.RUNNING.value,
                    started_at=datetime.now().isoformat(),
                )

                def _log(msg):
                    logger.info(f"[triage-ingest:{case_id[:8]}] {msg}")

                def _progress(completed, total):
                    background_task_storage.update_task(
                        task_id,
                        progress_completed=completed,
                        progress_total=total,
                    )

                result = ingest_bridge.ingest(
                    triage_case_id=case_id,
                    target_case_id=target_case_id,
                    file_ids=file_ids,
                    file_filter=file_filter,
                    include_artifacts=include_artifacts,
                    owner=owner,
                    log_callback=_log,
                    progress_callback=_progress,
                )

                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED.value,
                    completed_at=datetime.now().isoformat(),
                    metadata={
                        "triage_case_id": case_id,
                        "target_case_id": target_case_id,
                        "ingested_count": result.get("ingested_count", 0),
                        "skipped": result.get("skipped", 0),
                        "errors": result.get("errors", 0),
                    },
                )

            except Exception as e:
                logger.exception(f"Ingestion failed for triage case {case_id}")
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.FAILED.value,
                    error=str(e),
                    completed_at=datetime.now().isoformat(),
                )

        thread = threading.Thread(
            target=_run_ingest,
            daemon=False,
            name=f"triage-ingest-{case_id[:8]}",
        )
        thread.start()
        return task_id

    # ── File queries ──────────────────────────────────────────────────

    def get_scan_stats(self, case_id: str) -> Dict:
        """Get aggregate scan statistics from Neo4j."""
        driver = self._get_driver()
        with driver.session() as session:
            # Total files and size
            result = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                RETURN count(f) AS total_files,
                       coalesce(sum(f.size), 0) AS total_size,
                       count(DISTINCT f.sha256) AS unique_hashes,
                       sum(CASE WHEN f.extension_mismatch = true THEN 1 ELSE 0 END) AS extension_mismatches
                """,
                id=case_id,
            ).single()
            stats = {
                "total_files": result["total_files"],
                "total_size": result["total_size"],
                "unique_hashes": result["unique_hashes"],
                "extension_mismatches": result["extension_mismatches"],
            }

            # By category
            cats = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                RETURN f.category AS category, count(f) AS cnt, coalesce(sum(f.size), 0) AS total_size
                ORDER BY cnt DESC
                """,
                id=case_id,
            )
            stats["by_category"] = {}
            stats["by_category_size"] = {}
            for rec in cats:
                cat = rec["category"] or "other"
                stats["by_category"][cat] = rec["cnt"]
                stats["by_category_size"][cat] = rec["total_size"]

            # Top extensions
            exts = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                RETURN f.extension AS ext, count(f) AS cnt
                ORDER BY cnt DESC LIMIT 30
                """,
                id=case_id,
            )
            stats["by_extension"] = {rec["ext"] or "": rec["cnt"] for rec in exts}

            # OS from stored case
            case = triage_storage.get_case(case_id)
            stats["os_detected"] = case.get("scan_stats", {}).get("os_detected") if case else None

        return stats

    def get_files(
        self,
        case_id: str,
        skip: int = 0,
        limit: int = 50,
        sort_by: str = "relative_path",
        sort_dir: str = "asc",
        category: Optional[str] = None,
        extension: Optional[str] = None,
        hash_classification: Optional[str] = None,
        search: Optional[str] = None,
        path_prefix: Optional[str] = None,
        is_system_file: Optional[bool] = None,
        is_user_file: Optional[bool] = None,
        user_account: Optional[str] = None,
    ) -> Dict:
        """Paginated file listing from Neo4j."""
        driver = self._get_driver()

        # Build WHERE clauses
        where_clauses = ["f.triage_case_id = $case_id"]
        params: Dict = {"case_id": case_id, "skip": skip, "limit": limit}

        if category:
            where_clauses.append("f.category = $category")
            params["category"] = category
        if extension:
            where_clauses.append("f.extension = $extension")
            params["extension"] = extension
        if hash_classification:
            where_clauses.append("f.hash_classification = $hash_classification")
            params["hash_classification"] = hash_classification
        if search:
            where_clauses.append("toLower(f.filename) CONTAINS toLower($search)")
            params["search"] = search
        if path_prefix:
            where_clauses.append("f.relative_path STARTS WITH $path_prefix")
            params["path_prefix"] = path_prefix
        if is_system_file is not None:
            where_clauses.append("f.is_system_file = $is_system_file")
            params["is_system_file"] = is_system_file
        if is_user_file is not None:
            where_clauses.append("f.is_user_file = $is_user_file")
            params["is_user_file"] = is_user_file
        if user_account:
            where_clauses.append("f.user_account = $user_account")
            params["user_account"] = user_account

        where = " AND ".join(where_clauses)

        # Validate sort column
        valid_sorts = {
            "relative_path", "filename", "size", "category",
            "extension", "modified_time", "created_time",
            "hash_classification",
        }
        if sort_by not in valid_sorts:
            sort_by = "relative_path"
        direction = "DESC" if sort_dir.lower() == "desc" else "ASC"

        with driver.session() as session:
            # Count
            count_result = session.run(
                f"MATCH (f:TriageFile) WHERE {where} RETURN count(f) AS total",
                **params,
            ).single()
            total = count_result["total"] if count_result else 0

            # Fetch page
            rows = session.run(
                f"""
                MATCH (f:TriageFile)
                WHERE {where}
                RETURN f
                ORDER BY f.{sort_by} {direction}
                SKIP $skip LIMIT $limit
                """,
                **params,
            )
            files = []
            for row in rows:
                node = row["f"]
                files.append({
                    "id": node.get("relative_path", ""),
                    "relative_path": node.get("relative_path", ""),
                    "filename": node.get("filename", ""),
                    "extension": node.get("extension"),
                    "size": node.get("size", 0),
                    "sha256": node.get("sha256"),
                    "mime_type": node.get("mime_type"),
                    "magic_type": node.get("magic_type"),
                    "extension_mismatch": node.get("extension_mismatch", False),
                    "category": node.get("category"),
                    "subcategory": node.get("subcategory"),
                    "hash_classification": node.get("hash_classification"),
                    "hash_source": node.get("hash_source"),
                    "is_system_file": node.get("is_system_file"),
                    "is_user_file": node.get("is_user_file"),
                    "user_account": node.get("user_account"),
                    "created_time": node.get("created_time"),
                    "modified_time": node.get("modified_time"),
                    "accessed_time": node.get("accessed_time"),
                    "original_path": node.get("original_path"),
                })

        return {"files": files, "total": total, "skip": skip, "limit": limit}

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None


# Singleton
triage_service = TriageService()
