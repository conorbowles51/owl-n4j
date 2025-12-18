"""
Evidence Service

High-level operations for evidence files, including invoking the ingestion pipeline.
"""

from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import sys
import io
import contextlib

from config import BASE_DIR
from .evidence_storage import evidence_storage, EVIDENCE_ROOT_DIR
from .evidence_log_storage import evidence_log_storage
from services.neo4j_service import neo4j_service
from services.case_storage import case_storage
from services.cypher_generator import generate_cypher_from_graph


def _import_ingest_file():
    """
    Dynamically import ingest_file from ingestion/scripts/ingest_data.py.

    Returns:
        ingest_file callable or raises ImportError.
    """
    # BASE_DIR is the project root (e.g. /.../owl-n4j)
    scripts_dir = BASE_DIR / "ingestion" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.append(str(scripts_dir))

    # Import from the ingestion CLI module
    from ingest_data import ingest_file  # type: ignore

    return ingest_file


class EvidenceService:
    """Orchestrates evidence processing and integration with ingest_data.py."""

    def __init__(self) -> None:
        self._ingest_file = None

    def _ensure_ingest(self):
        if self._ingest_file is None:
            self._ingest_file = _import_ingest_file()

    def list_files(
        self,
        case_id: Optional[str] = None,
        status: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> List[Dict]:
        """Proxy to evidence_storage.list_files."""
        return evidence_storage.list_files(case_id=case_id, status=status, owner=owner)

    def add_uploaded_files(
        self,
        case_id: str,
        uploads: List[Dict],
        owner: Optional[str] = None,
    ) -> List[Dict]:
        """
        Store uploaded files and register them in evidence storage.

        Args:
            case_id: Associated case ID
            uploads: List of dicts:
                {
                  "original_filename": str,
                  "content": bytes,
                }
        """
        case_dir = EVIDENCE_ROOT_DIR / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        file_infos = []
        for upload in uploads:
            original_filename = upload["original_filename"]
            content: bytes = upload["content"]
            stored_path = case_dir / original_filename
            # Overwrite existing file with same name
            stored_path.write_bytes(content)
            file_infos.append(
                {
                    "original_filename": original_filename,
                    "stored_path": stored_path,
                    "content": content,
                    "size": len(content),
                }
            )

        return evidence_storage.add_files(case_id=case_id, files=file_infos, owner=owner)

    def process_files(
        self,
        evidence_ids: List[str],
        case_id: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> Dict:
        """
        Process selected evidence files using ingest_data.ingest_file.

        Args:
            evidence_ids: List of evidence IDs to process
            case_id: Optional case ID. If provided and files are processed,
                a new case version will be saved with Cypher to recreate
                the current graph.

        Returns:
            Summary dict with counts. Case information may be added
            (case_id, case_version, case_timestamp) when applicable.
        """
        if not evidence_ids:
            return {"processed": 0, "skipped": 0, "errors": 0}

        # Ensure the ingest_file function is available
        self._ensure_ingest()

        # High-level log entry
        evidence_log_storage.add_log(
            case_id=case_id,
            evidence_id=None,
            filename=None,
            level="info",
            message=f"Starting ingestion for {len(evidence_ids)} evidence file(s).",
        )

        records = [evidence_storage.get(eid) for eid in evidence_ids]
        # Only process records that belong to this owner (if provided)
        records = [
            r for r in records
            if r is not None and (owner is None or r.get("owner") == owner)
        ]

        if not records:
            return {"processed": 0, "skipped": 0, "errors": 0}

        # Group by sha256 so duplicates are only processed once per request
        by_hash: Dict[str, List[dict]] = {}
        for rec in records:
            sha = rec.get("sha256")
            if not sha:
                continue
            by_hash.setdefault(sha, []).append(rec)

        processed = 0
        skipped = 0
        errors = 0

        # For progress reporting: one batch per unique file hash
        total_batches = len(by_hash)
        completed_batches = 0

        for sha, recs in by_hash.items():
            # Use the first record to get stored_path and metadata
            primary = recs[0]
            path_str = primary.get("stored_path")
            evidence_id = primary.get("id")
            filename = primary.get("original_filename")

            if not path_str:
                errors += len(recs)
                evidence_storage.mark_processed(
                    [r["id"] for r in recs],
                    error="Missing stored_path",
                )
                if case_id:
                    evidence_log_storage.add_log(
                        case_id=case_id,
                        evidence_id=evidence_id,
                        filename=filename,
                        level="error",
                        message="Skipping file: stored_path missing in evidence record.",
                    )
                continue

            path = Path(path_str)

            # Log start of file ingestion (with overall progress hint)
            if case_id:
                evidence_log_storage.add_log(
                    case_id=case_id,
                    evidence_id=evidence_id,
                    filename=filename,
                    level="info",
                    message=f"Ingesting file '{filename}' from {path}",
                    progress_current=completed_batches,
                    progress_total=total_batches,
                )

            # Capture console output from ingest_file so the UI can display it
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    self._ingest_file(path)

                ingest_output = buf.getvalue()
                if case_id and ingest_output.strip():
                    evidence_log_storage.add_log(
                        case_id=case_id,
                        evidence_id=evidence_id,
                        filename=filename,
                        level="debug",
                        message=ingest_output,
                    )

                # Mark all records with this hash as processed
                evidence_storage.mark_processed(
                    [r["id"] for r in recs],
                    error=None,
                )
                processed += len(recs)

                if case_id:
                    completed_batches += 1
                    evidence_log_storage.add_log(
                        case_id=case_id,
                        evidence_id=evidence_id,
                        filename=filename,
                        level="info",
                        message=f"Completed ingestion for '{filename}'.",
                        progress_current=completed_batches,
                        progress_total=total_batches,
                    )
            except Exception as e:  # pragma: no cover - defensive
                errors += len(recs)
                evidence_storage.mark_processed(
                    [r["id"] for r in recs],
                    error=str(e),
                )
                if case_id:
                    evidence_log_storage.add_log(
                        case_id=case_id,
                        evidence_id=evidence_id,
                        filename=filename,
                        level="error",
                        message=f"Ingestion failed for '{filename}': {e}",
                    )

        summary: Dict[str, object] = {
            "processed": processed,
            "skipped": skipped,
            "errors": errors,
        }

        # If we have an associated case and at least one file was processed,
        # capture the current graph as Cypher and append it as a new case version.
        if case_id and processed > 0:
            try:
                # Get current full graph (nodes + links)
                graph_data = neo4j_service.get_full_graph()

                # Generate Cypher to recreate this graph
                cypher_queries = generate_cypher_from_graph(graph_data)

                # Look up case name (fallback to case_id if not found)
                case = case_storage.get_case(case_id)
                case_name = case["name"] if case and case.get("name") else case_id

                # Save as a new version on this case
                case_result = case_storage.save_case_version(
                    case_id=case_id,
                    case_name=case_name,
                    cypher_queries=cypher_queries,
                    snapshots=[],
                    save_notes=f"Auto-save after processing {processed} evidence file(s).",
                )

                summary["case_id"] = case_result.get("case_id")
                summary["case_version"] = case_result.get("version")
                summary["case_timestamp"] = case_result.get("timestamp")

                evidence_log_storage.add_log(
                    case_id=case_id,
                    evidence_id=None,
                    filename=None,
                    level="info",
                    message=(
                        "Saved new case version after evidence processing: "
                        f"case_id={case_result.get('case_id')}, "
                        f"version={case_result.get('version')}."
                    ),
                )
            except Exception as e:  # pragma: no cover - defensive
                # Do not fail evidence processing if case saving fails; just log.
                print(f"Warning: failed to attach graph Cypher to case {case_id}: {e}")
                evidence_log_storage.add_log(
                    case_id=case_id,
                    evidence_id=None,
                    filename=None,
                    level="error",
                    message=f"Failed to save case version after evidence processing: {e}",
                )

        return summary


# Singleton instance
evidence_service = EvidenceService()


