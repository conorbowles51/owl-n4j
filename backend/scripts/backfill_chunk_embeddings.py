"""
Backfill chunk embeddings for evidence files stored in Postgres.

This script reads EvidenceFile rows, re-extracts text from their stored files,
chunks the text, embeds each chunk, and writes chunk embeddings to ChromaDB.
It does not read or write legacy JSON evidence storage.
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import select


project_root = Path(__file__).parent.parent.parent
backend_dir = project_root / "backend"
ingestion_dir = project_root / "ingestion" / "scripts"

if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

if str(ingestion_dir) not in sys.path:
    sys.path.append(str(ingestion_dir))

from postgres.models.evidence import EvidenceFile
from postgres.session import get_background_session
from routers.backfill import extract_text_from_file
from services.embedding_service import embedding_service
from services.neo4j_service import neo4j_service
from services.vector_db_service import vector_db_service

from chunking import chunk_document


def _log(log_callback, level: str, message: str) -> None:
    print(f"[{level.upper()}] {message}")
    if log_callback:
        log_callback(level, message)


def _coerce_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _resolve_path(stored_path: str | None) -> Path | None:
    if not stored_path:
        return None

    candidates = []
    raw_path = Path(stored_path)
    candidates.append(raw_path)
    if not raw_path.is_absolute():
        candidates.append(backend_dir / raw_path)
        candidates.append(project_root / raw_path)

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _load_evidence_files(case_id: str | None) -> list[EvidenceFile]:
    case_uuid = _coerce_uuid(case_id)
    with get_background_session() as db:
        query = select(EvidenceFile).order_by(EvidenceFile.original_filename)
        if case_uuid:
            query = query.where(EvidenceFile.case_id == case_uuid)
        return list(db.scalars(query).all())


def _find_graph_document(file: EvidenceFile) -> dict[str, Any]:
    params = {
        "case_id": str(file.case_id),
        "name": file.original_filename,
        "file_id": str(file.id),
        "legacy_id": file.legacy_id or "",
    }
    try:
        rows = neo4j_service.run_cypher(
            """
            MATCH (d:Document {case_id: $case_id})
            WHERE d.name = $name
               OR d.id = $file_id
               OR ($legacy_id <> '' AND d.id = $legacy_id)
               OR d.vector_db_id = $file_id
               OR ($legacy_id <> '' AND d.vector_db_id = $legacy_id)
            RETURN d.id AS id,
                   d.key AS key,
                   d.name AS name,
                   d.case_id AS case_id,
                   COALESCE(d.vector_db_id, null) AS vector_db_id
            ORDER BY CASE WHEN d.name = $name THEN 0 ELSE 1 END
            LIMIT 1
            """,
            params,
        )
    except Exception:
        rows = []

    if rows:
        return dict(rows[0])

    return {
        "id": file.legacy_id or str(file.id),
        "key": "",
        "name": file.original_filename,
        "case_id": str(file.case_id),
        "vector_db_id": None,
    }


def _set_vector_db_id(doc_id: str) -> None:
    try:
        neo4j_service.run_cypher(
            "MATCH (d:Document {id: $doc_id}) SET d.vector_db_id = $doc_id",
            {"doc_id": doc_id},
        )
    except Exception:
        # Chunks are still useful even if the graph node is missing or offline.
        pass


def backfill_chunk_embeddings(
    dry_run: bool = False,
    skip_existing: bool = True,
    case_id: Optional[str] = None,
    batch_size: int = 10,
    log_callback=None,
) -> Dict[str, Any]:
    """
    Generate chunk-level embeddings from Postgres EvidenceFile rows.
    """
    _log(log_callback, "info", "=" * 60)
    _log(log_callback, "info", "Backfilling chunk embeddings from Postgres evidence")
    _log(log_callback, "info", "=" * 60)

    if embedding_service is None:
        _log(log_callback, "error", "Embedding service is not configured")
        return {"status": "error", "reason": "embedding_service_not_configured"}

    if vector_db_service is None:
        _log(log_callback, "error", "Vector database service is not configured")
        return {"status": "error", "reason": "vector_db_service_not_configured"}

    if case_id and _coerce_uuid(case_id) is None:
        _log(log_callback, "error", f"Invalid case_id: {case_id}")
        return {"status": "error", "reason": "invalid_case_id"}

    files = _load_evidence_files(case_id)
    if not files:
        _log(log_callback, "info", "No evidence files found")
        return {"status": "complete", "stats": {"total": 0, "processed": 0}}

    stats: dict[str, Any] = {
        "total": len(files),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "already_has_chunks": 0,
        "file_not_found": 0,
        "extraction_failed": 0,
        "embedding_failed": 0,
        "total_chunks_created": 0,
        "file_not_found_names": [],
    }

    if dry_run:
        _log(log_callback, "info", "[DRY RUN MODE] - No changes will be made")

    start_time = time.time()

    for index, file in enumerate(files, 1):
        graph_doc = _find_graph_document(file)
        doc_id = str(graph_doc.get("id") or file.legacy_id or file.id)
        doc_key = str(graph_doc.get("key") or "")
        doc_name = str(graph_doc.get("name") or file.original_filename)
        doc_case_id = str(graph_doc.get("case_id") or file.case_id)

        if skip_existing:
            try:
                existing_chunks = vector_db_service.chunk_collection.get(where={"doc_id": doc_id}, include=[])
                if existing_chunks and existing_chunks.get("ids"):
                    _log(
                        log_callback,
                        "info",
                        f"[{index}/{stats['total']}] {doc_name} - already has chunks",
                    )
                    stats["already_has_chunks"] += 1
                    continue
            except Exception as exc:
                _log(log_callback, "warning", f"Could not check existing chunks for {doc_name}: {exc}")

        _log(log_callback, "info", f"[{index}/{stats['total']}] Processing {doc_name}")

        file_path = _resolve_path(file.stored_path)
        if file_path is None:
            _log(log_callback, "warning", f"File not found on disk for {doc_name}")
            stats["file_not_found"] += 1
            stats["file_not_found_names"].append(doc_name)
            continue

        try:
            text = extract_text_from_file(file_path)
            if not text or not text.strip():
                raise ValueError("text extraction returned no content")
        except Exception as exc:
            _log(log_callback, "error", f"Text extraction failed for {doc_name}: {exc}")
            stats["extraction_failed"] += 1
            continue

        try:
            chunks = chunk_document(text, doc_name)
            if not chunks:
                raise ValueError("chunker returned no chunks")
        except Exception as exc:
            _log(log_callback, "error", f"Chunking failed for {doc_name}: {exc}")
            stats["extraction_failed"] += 1
            continue

        if dry_run:
            stats["processed"] += 1
            stats["total_chunks_created"] += len(chunks)
            _log(log_callback, "info", f"[DRY RUN] Would create {len(chunks)} chunks for {doc_name}")
            continue

        chunks_stored = 0
        for chunk_index, chunk_data in enumerate(chunks):
            chunk_text = str(chunk_data.get("text") or "")
            if not chunk_text.strip():
                continue

            try:
                embedding = embedding_service.generate_embedding(chunk_text)
                if not embedding:
                    raise ValueError("embedding service returned an empty vector")
            except Exception as exc:
                stats["embedding_failed"] += 1
                _log(log_callback, "error", f"Embedding failed for {doc_name} chunk {chunk_index}: {exc}")
                continue

            metadata = {
                "doc_id": doc_id,
                "doc_name": doc_name,
                "doc_key": doc_key,
                "case_id": doc_case_id,
                "evidence_file_id": str(file.id),
                "legacy_id": file.legacy_id or "",
                "owner": file.owner or "",
                "source_type": file.source_type or file_path.suffix.lower().lstrip(".") or "unknown",
                "chunk_index": chunk_index,
                "total_chunks": len(chunks),
                "page_start": chunk_data.get("page_start", -1) or -1,
                "page_end": chunk_data.get("page_end", -1) or -1,
            }

            try:
                vector_db_service.add_chunk(
                    chunk_id=f"{doc_id}_chunk_{chunk_index}",
                    text=chunk_text,
                    embedding=embedding,
                    metadata=metadata,
                )
                chunks_stored += 1
            except Exception as exc:
                stats["embedding_failed"] += 1
                _log(log_callback, "error", f"Failed storing {doc_name} chunk {chunk_index}: {exc}")

        if chunks_stored:
            _set_vector_db_id(doc_id)
            stats["processed"] += 1
            stats["total_chunks_created"] += chunks_stored
            _log(log_callback, "info", f"Stored {chunks_stored}/{len(chunks)} chunks for {doc_name}")
        else:
            stats["failed"] += 1
            _log(log_callback, "error", f"No chunks stored for {doc_name}")

        if index % batch_size == 0:
            elapsed = max(time.time() - start_time, 0.001)
            rate = index / elapsed
            remaining = stats["total"] - index
            eta = remaining / rate if rate > 0 else 0
            _log(
                log_callback,
                "info",
                f"Progress: {index}/{stats['total']} ({index / stats['total'] * 100:.1f}%), ETA {eta:.0f}s",
            )

    elapsed = time.time() - start_time
    _log(log_callback, "info", "=" * 60)
    _log(
        log_callback,
        "info",
        f"Chunk backfill complete: {stats['processed']} processed, "
        f"{stats['already_has_chunks']} already had chunks, {stats['failed']} failed",
    )

    return {"status": "complete", "stats": stats, "elapsed_seconds": elapsed}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Backfill chunk embeddings from Postgres evidence")
    parser.add_argument("--dry-run", action="store_true", help="Run without making changes")
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--no-skip-existing", action="store_false", dest="skip_existing")
    parser.add_argument("--case-id", type=str, default=None, help="Only process this case UUID")
    parser.add_argument("--batch-size", type=int, default=10)

    args = parser.parse_args()
    result = backfill_chunk_embeddings(
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
        case_id=args.case_id,
        batch_size=args.batch_size,
    )
    if result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
