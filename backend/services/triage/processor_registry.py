"""
Processor Registry

Discovers and manages triage file processors.
Auto-discovers processors from the triage_processors package.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from services.triage_processors.base_processor import BaseTriageProcessor, ProcessingResult

logger = logging.getLogger(__name__)

# ── Neo4j queries ────────────────────────────────────────────────────

_CREATE_ARTIFACT = """
UNWIND $batch AS art
MATCH (f:TriageFile {triage_case_id: $case_id, original_path: art.source_path})
CREATE (a:ProcessedArtifact {
    id: art.id,
    triage_case_id: $case_id,
    stage_id: $stage_id,
    processor_name: $processor_name,
    artifact_type: art.artifact_type,
    content: art.content,
    metadata: art.metadata,
    created_at: datetime(),
    error: art.error
})
CREATE (a)-[:DERIVED_FROM]->(f)
CREATE (a)-[:PRODUCED_BY]->(:TriageStage {id: $stage_id, triage_case_id: $case_id})
"""

_ENSURE_ARTIFACT_INDEXES = """
CREATE INDEX processed_artifact_case IF NOT EXISTS FOR (a:ProcessedArtifact) ON (a.triage_case_id)
"""

_ENSURE_ARTIFACT_STAGE_INDEX = """
CREATE INDEX processed_artifact_stage IF NOT EXISTS FOR (a:ProcessedArtifact) ON (a.triage_case_id, a.stage_id)
"""


class ProcessorRegistry:
    """Manages and executes triage processors."""

    def __init__(self):
        self._processors: Dict[str, BaseTriageProcessor] = {}
        self._driver = None
        self._loaded = False

    def _get_driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            # Ensure indexes
            with self._driver.session() as session:
                try:
                    session.run(_ENSURE_ARTIFACT_INDEXES)
                    session.run(_ENSURE_ARTIFACT_STAGE_INDEX)
                except Exception:
                    pass
        return self._driver

    def _ensure_loaded(self):
        """Auto-discover and register all built-in processors."""
        if self._loaded:
            return
        self._loaded = True

        # Import built-in processors
        try:
            from services.triage_processors.text_extractor import TextExtractorProcessor
            self.register(TextExtractorProcessor())
        except ImportError as e:
            logger.warning(f"Could not load text_extractor: {e}")

        try:
            from services.triage_processors.exif_processor import ExifProcessor
            self.register(ExifProcessor())
        except ImportError as e:
            logger.warning(f"Could not load exif_processor: {e}")

        try:
            from services.triage_processors.browser_processor import BrowserProcessor
            self.register(BrowserProcessor())
        except ImportError as e:
            logger.warning(f"Could not load browser_processor: {e}")

        try:
            from services.triage_processors.email_processor import EmailProcessor
            self.register(EmailProcessor())
        except ImportError as e:
            logger.warning(f"Could not load email_processor: {e}")

        try:
            from services.triage_processors.llm_processor import LLMProcessor
            self.register(LLMProcessor())
        except ImportError as e:
            logger.warning(f"Could not load llm_processor: {e}")

    def register(self, processor: BaseTriageProcessor):
        """Register a processor."""
        self._processors[processor.name] = processor
        logger.info(f"Registered triage processor: {processor.name}")

    def list_processors(self) -> List[Dict]:
        """List all registered processors."""
        self._ensure_loaded()
        return [p.get_info() for p in self._processors.values()]

    def get_processor(self, name: str) -> Optional[BaseTriageProcessor]:
        """Get a processor by name."""
        self._ensure_loaded()
        return self._processors.get(name)

    def execute_stage(
        self,
        triage_case_id: str,
        stage_id: str,
        processor_name: str,
        config: Dict[str, Any],
        file_filter: Dict[str, Any],
        max_workers: int = 4,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict:
        """
        Execute a processing stage on matching files.

        Args:
            triage_case_id: Case ID
            stage_id: Stage ID for provenance tracking
            processor_name: Name of the processor to use
            config: Processor configuration
            file_filter: Filter criteria for selecting files
            max_workers: Thread pool workers for parallel processing
            log_callback: Logging callback
            progress_callback: fn(completed, total)

        Returns:
            Dict with execution statistics
        """
        self._ensure_loaded()
        driver = self._get_driver()

        processor = self._processors.get(processor_name)
        if not processor:
            raise ValueError(f"Unknown processor: {processor_name}")

        def _log(msg):
            if log_callback:
                log_callback(msg)
            logger.info(msg)

        # 1. Get matching files
        _log(f"Querying files matching filter for processor '{processor_name}'...")
        files = self._get_matching_files(driver, triage_case_id, file_filter)
        total = len(files)
        _log(f"Found {total:,} matching files")

        if total == 0:
            return {"total_files": 0, "artifacts_created": 0, "errors": 0}

        # 2. Process files
        artifacts_created = 0
        errors = 0
        artifact_batch = []

        def _process_one(file_data):
            try:
                return processor.process_file(
                    file_path=file_data["original_path"],
                    file_info=file_data,
                    config=config,
                )
            except Exception as e:
                return [ProcessingResult(
                    source_path=file_data["original_path"],
                    artifact_type="error",
                    error=str(e),
                )]

        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_one, f): f for f in files}
            for future in as_completed(futures):
                results = future.result()
                for result in results:
                    artifact_batch.append({
                        "id": str(uuid4()),
                        "source_path": result.source_path,
                        "artifact_type": result.artifact_type,
                        "content": result.content,
                        "metadata": json.dumps(result.metadata) if result.metadata else "{}",
                        "error": result.error,
                    })
                    if result.success:
                        artifacts_created += 1
                    else:
                        errors += 1

                completed += 1
                if completed % 50 == 0:
                    # Flush batch
                    if artifact_batch:
                        self._write_artifacts(driver, triage_case_id, stage_id, processor_name, artifact_batch)
                        artifact_batch = []
                    if progress_callback:
                        progress_callback(completed, total)
                    _log(f"Processed {completed:,}/{total:,} files")

        # Flush remaining
        if artifact_batch:
            self._write_artifacts(driver, triage_case_id, stage_id, processor_name, artifact_batch)

        _log(f"Stage complete: {artifacts_created:,} artifacts, {errors:,} errors")
        return {
            "total_files": total,
            "artifacts_created": artifacts_created,
            "errors": errors,
        }

    def _get_matching_files(
        self, driver, triage_case_id: str, file_filter: Dict[str, Any]
    ) -> List[Dict]:
        """Get files matching the filter criteria."""
        where = ["f.triage_case_id = $case_id"]
        params: Dict[str, Any] = {"case_id": triage_case_id}

        if file_filter.get("category"):
            where.append("f.category = $category")
            params["category"] = file_filter["category"]
        if file_filter.get("categories"):
            where.append("f.category IN $categories")
            params["categories"] = file_filter["categories"]
        if file_filter.get("extension"):
            where.append("f.extension = $extension")
            params["extension"] = file_filter["extension"]
        if file_filter.get("extensions"):
            where.append("f.extension IN $extensions")
            params["extensions"] = file_filter["extensions"]
        if file_filter.get("path_prefix"):
            where.append("f.relative_path STARTS WITH $path_prefix")
            params["path_prefix"] = file_filter["path_prefix"]
        if file_filter.get("hash_classification"):
            where.append("f.hash_classification = $hash_classification")
            params["hash_classification"] = file_filter["hash_classification"]
        if file_filter.get("is_user_file") is not None:
            where.append("f.is_user_file = $is_user_file")
            params["is_user_file"] = file_filter["is_user_file"]
        if file_filter.get("user_account"):
            where.append("f.user_account = $user_account")
            params["user_account"] = file_filter["user_account"]

        query = f"""
        MATCH (f:TriageFile)
        WHERE {' AND '.join(where)}
        RETURN f.relative_path AS relative_path,
               f.filename AS filename,
               f.extension AS extension,
               f.original_path AS original_path,
               f.category AS category,
               f.mime_type AS mime_type,
               f.sha256 AS sha256,
               f.size AS size
        """

        with driver.session() as session:
            result = session.run(query, **params)
            return [dict(rec) for rec in result]

    def _write_artifacts(
        self, driver, case_id: str, stage_id: str, processor_name: str, batch: List[Dict]
    ):
        """Write artifact batch to Neo4j."""
        if not batch:
            return
        # Use simpler creation without MATCH for better performance
        with driver.session() as session:
            session.run(
                """
                UNWIND $batch AS art
                CREATE (a:ProcessedArtifact {
                    id: art.id,
                    triage_case_id: $case_id,
                    stage_id: $stage_id,
                    processor_name: $processor_name,
                    artifact_type: art.artifact_type,
                    content: art.content,
                    metadata: art.metadata,
                    source_path: art.source_path,
                    error: art.error,
                    created_at: datetime()
                })
                """,
                batch=batch,
                case_id=case_id,
                stage_id=stage_id,
                processor_name=processor_name,
            )
            # Create DERIVED_FROM relationships separately
            session.run(
                """
                UNWIND $batch AS art
                MATCH (a:ProcessedArtifact {id: art.id, triage_case_id: $case_id})
                MATCH (f:TriageFile {triage_case_id: $case_id, original_path: art.source_path})
                MERGE (a)-[:DERIVED_FROM]->(f)
                """,
                batch=batch,
                case_id=case_id,
            )

    def get_stage_results(self, triage_case_id: str, stage_id: str) -> List[Dict]:
        """Get artifacts produced by a stage."""
        driver = self._get_driver()
        with driver.session() as session:
            result = session.run(
                """
                MATCH (a:ProcessedArtifact {triage_case_id: $case_id, stage_id: $stage_id})
                RETURN a.id AS id, a.artifact_type AS artifact_type,
                       a.content AS content, a.metadata AS metadata,
                       a.source_path AS source_path, a.error AS error,
                       a.processor_name AS processor_name,
                       a.created_at AS created_at
                ORDER BY a.created_at DESC
                LIMIT 500
                """,
                case_id=triage_case_id,
                stage_id=stage_id,
            )
            return [
                {
                    "id": rec["id"],
                    "artifact_type": rec["artifact_type"],
                    "content": rec["content"],
                    "metadata": json.loads(rec["metadata"]) if rec["metadata"] else {},
                    "source_path": rec["source_path"],
                    "error": rec["error"],
                    "processor_name": rec["processor_name"],
                    "created_at": str(rec["created_at"]) if rec["created_at"] else None,
                }
                for rec in result
            ]

    def get_file_provenance(self, triage_case_id: str, file_path: str) -> Dict:
        """Get provenance chain for a file."""
        driver = self._get_driver()
        with driver.session() as session:
            # Get file info
            file_result = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $case_id, relative_path: $path})
                RETURN f
                """,
                case_id=triage_case_id,
                path=file_path,
            ).single()

            if not file_result:
                return {"file": None, "artifacts": []}

            node = file_result["f"]
            file_info = {k: node[k] for k in node.keys()}

            # Get artifacts derived from this file
            artifacts = session.run(
                """
                MATCH (a:ProcessedArtifact)-[:DERIVED_FROM]->(f:TriageFile {triage_case_id: $case_id, relative_path: $path})
                RETURN a.id AS id, a.artifact_type AS type, a.processor_name AS processor,
                       a.stage_id AS stage_id, a.content AS content, a.metadata AS metadata,
                       a.created_at AS created_at
                ORDER BY a.created_at
                """,
                case_id=triage_case_id,
                path=file_path,
            )

            return {
                "file": file_info,
                "artifacts": [
                    {
                        "id": rec["id"],
                        "type": rec["type"],
                        "processor": rec["processor"],
                        "stage_id": rec["stage_id"],
                        "content": rec["content"],
                        "metadata": json.loads(rec["metadata"]) if rec["metadata"] else {},
                        "created_at": str(rec["created_at"]) if rec["created_at"] else None,
                    }
                    for rec in artifacts
                ],
            }

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None


# Singleton
processor_registry = ProcessorRegistry()
