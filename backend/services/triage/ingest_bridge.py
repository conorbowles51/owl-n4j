"""
Ingest Bridge

Bridges triage files and processed artifacts into Owl investigation cases.
Copies selected files to evidence storage, registers them, and optionally
triggers evidence processing. Creates INGESTED_AS provenance relationships.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from services.background_task_storage import background_task_storage, TaskStatus
from services.triage.triage_storage import triage_storage

logger = logging.getLogger(__name__)


class IngestBridge:
    """Bridges triage data into Owl investigation cases."""

    def __init__(self):
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
        return self._driver

    def preview(
        self,
        triage_case_id: str,
        file_ids: List[str] = None,
        file_filter: Optional[Dict[str, Any]] = None,
        include_artifacts: bool = True,
    ) -> Dict:
        """
        Preview what would be ingested.

        Args:
            triage_case_id: Source triage case
            file_ids: Specific file relative_paths to ingest (None = use filter)
            file_filter: Filter criteria if file_ids not provided
            include_artifacts: Whether to include processed artifacts

        Returns:
            Dict with file_count, total_size, artifact_count
        """
        driver = self._get_driver()

        with driver.session() as session:
            if file_ids:
                # Count specific files
                result = session.run(
                    """
                    MATCH (f:TriageFile {triage_case_id: $case_id})
                    WHERE f.relative_path IN $file_ids
                    RETURN count(f) AS file_count,
                           coalesce(sum(f.size), 0) AS total_size
                    """,
                    case_id=triage_case_id,
                    file_ids=file_ids,
                ).single()
            elif file_filter:
                where, params = self._build_filter(triage_case_id, file_filter)
                result = session.run(
                    f"""
                    MATCH (f:TriageFile)
                    WHERE {where}
                    RETURN count(f) AS file_count,
                           coalesce(sum(f.size), 0) AS total_size
                    """,
                    **params,
                ).single()
            else:
                return {"file_count": 0, "total_size": 0, "artifact_count": 0}

            file_count = result["file_count"]
            total_size = result["total_size"]

            # Count artifacts
            artifact_count = 0
            if include_artifacts and file_ids:
                art_result = session.run(
                    """
                    MATCH (a:ProcessedArtifact)-[:DERIVED_FROM]->(f:TriageFile {triage_case_id: $case_id})
                    WHERE f.relative_path IN $file_ids AND a.error IS NULL
                    RETURN count(a) AS cnt
                    """,
                    case_id=triage_case_id,
                    file_ids=file_ids,
                ).single()
                artifact_count = art_result["cnt"]

        return {
            "file_count": file_count,
            "total_size": total_size,
            "artifact_count": artifact_count,
        }

    def ingest(
        self,
        triage_case_id: str,
        target_case_id: str,
        file_ids: List[str] = None,
        file_filter: Optional[Dict[str, Any]] = None,
        include_artifacts: bool = True,
        owner: str = "",
        log_callback=None,
        progress_callback=None,
    ) -> Dict:
        """
        Ingest selected triage files into an Owl investigation case.

        Args:
            triage_case_id: Source triage case
            target_case_id: Target Owl case ID
            file_ids: Specific file relative_paths
            file_filter: Filter criteria if file_ids not provided
            include_artifacts: Include processed artifacts
            owner: User performing the ingestion
            log_callback: fn(msg)
            progress_callback: fn(completed, total)

        Returns:
            Dict with ingested_count, skipped, errors
        """
        from services.evidence_service import evidence_service

        def _log(msg):
            if log_callback:
                log_callback(msg)
            logger.info(msg)

        driver = self._get_driver()

        # 1. Get files to ingest
        files = self._get_files(driver, triage_case_id, file_ids, file_filter)
        total = len(files)
        _log(f"Ingesting {total:,} files from triage case into case {target_case_id}")

        if total == 0:
            return {"ingested_count": 0, "skipped": 0, "errors": 0}

        ingested = 0
        skipped = 0
        errors = 0

        # 2. Process in batches
        batch_size = 50
        for i in range(0, total, batch_size):
            batch = files[i:i + batch_size]
            uploads = []

            for f in batch:
                original_path = f.get("original_path", "")
                if not original_path or not Path(original_path).exists():
                    skipped += 1
                    continue

                try:
                    content = Path(original_path).read_bytes()
                    uploads.append({
                        "original_filename": f.get("filename", Path(original_path).name),
                        "content": content,
                        "relative_path": f.get("relative_path"),
                    })
                except Exception as e:
                    _log(f"Error reading {original_path}: {e}")
                    errors += 1
                    continue

            if uploads:
                try:
                    records = evidence_service.add_uploaded_files(
                        case_id=target_case_id,
                        uploads=uploads,
                        owner=owner,
                        preserve_structure=True,
                    )
                    ingested += len(records)

                    # Create INGESTED_AS provenance relationships in Neo4j
                    self._create_provenance(
                        driver, triage_case_id, target_case_id, batch, records
                    )
                except Exception as e:
                    _log(f"Error ingesting batch: {e}")
                    errors += len(uploads)

            completed = min(i + batch_size, total)
            if progress_callback:
                progress_callback(completed, total)
            _log(f"Ingested {completed:,}/{total:,} files")

        # 3. Optionally submit for processing
        if ingested > 0:
            _log(f"Ingestion complete: {ingested:,} files added to case {target_case_id}")

        return {
            "ingested_count": ingested,
            "skipped": skipped,
            "errors": errors,
            "target_case_id": target_case_id,
        }

    def _get_files(
        self, driver, triage_case_id: str,
        file_ids: List[str] = None,
        file_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        """Get files to ingest from Neo4j."""
        with driver.session() as session:
            if file_ids:
                result = session.run(
                    """
                    MATCH (f:TriageFile {triage_case_id: $case_id})
                    WHERE f.relative_path IN $file_ids
                    RETURN f.relative_path AS relative_path,
                           f.filename AS filename,
                           f.original_path AS original_path,
                           f.sha256 AS sha256,
                           f.size AS size
                    """,
                    case_id=triage_case_id,
                    file_ids=file_ids,
                )
            elif file_filter:
                where, params = self._build_filter(triage_case_id, file_filter)
                result = session.run(
                    f"""
                    MATCH (f:TriageFile)
                    WHERE {where}
                    RETURN f.relative_path AS relative_path,
                           f.filename AS filename,
                           f.original_path AS original_path,
                           f.sha256 AS sha256,
                           f.size AS size
                    """,
                    **params,
                )
            else:
                return []

            return [dict(rec) for rec in result]

    def _build_filter(
        self, triage_case_id: str, file_filter: Dict[str, Any]
    ) -> tuple:
        """Build WHERE clause from filter dict."""
        where = ["f.triage_case_id = $case_id"]
        params = {"case_id": triage_case_id}

        if file_filter.get("category"):
            where.append("f.category = $category")
            params["category"] = file_filter["category"]
        if file_filter.get("categories"):
            where.append("f.category IN $categories")
            params["categories"] = file_filter["categories"]
        if file_filter.get("extension"):
            where.append("f.extension = $extension")
            params["extension"] = file_filter["extension"]
        if file_filter.get("hash_classification"):
            where.append("f.hash_classification = $hash_classification")
            params["hash_classification"] = file_filter["hash_classification"]
        if file_filter.get("is_user_file") is not None:
            where.append("f.is_user_file = $is_user_file")
            params["is_user_file"] = file_filter["is_user_file"]
        if file_filter.get("path_prefix"):
            where.append("f.relative_path STARTS WITH $path_prefix")
            params["path_prefix"] = file_filter["path_prefix"]

        return " AND ".join(where), params

    def _create_provenance(
        self, driver, triage_case_id: str, target_case_id: str,
        triage_files: List[Dict], evidence_records: List[Dict],
    ):
        """Create INGESTED_AS relationships between triage files and evidence."""
        # Build hash→evidence_id mapping
        hash_to_evidence = {}
        for rec in evidence_records:
            sha = rec.get("sha256")
            if sha:
                hash_to_evidence[sha] = rec.get("id", "")

        # Match by hash
        batch = []
        for tf in triage_files:
            sha = tf.get("sha256")
            if sha and sha in hash_to_evidence:
                batch.append({
                    "relative_path": tf.get("relative_path"),
                    "evidence_id": hash_to_evidence[sha],
                })

        if not batch:
            return

        with driver.session() as session:
            session.run(
                """
                UNWIND $batch AS item
                MATCH (tf:TriageFile {triage_case_id: $triage_case_id, relative_path: item.relative_path})
                MERGE (tf)-[:INGESTED_AS {target_case_id: $target_case_id}]->(:IngestedEvidence {
                    evidence_id: item.evidence_id,
                    target_case_id: $target_case_id,
                    ingested_at: datetime()
                })
                """,
                batch=batch,
                triage_case_id=triage_case_id,
                target_case_id=target_case_id,
            )

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None


# Singleton
ingest_bridge = IngestBridge()
