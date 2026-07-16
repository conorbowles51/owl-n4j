from __future__ import annotations

import hashlib
import mimetypes
import re
import uuid
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import EVIDENCE_DATA_ROOT
from postgres.models.chat import ChatCitationSnapshot
from postgres.models.evidence import EvidenceFile
from postgres.models.graph_recycle_bin import GraphRecycleBinItem
from utils.text_sanitize import sanitize_json, sanitize_text


WARNING_BY_STATUS = {
    "available": None,
    "deleted": "The cited source is no longer present in the case evidence.",
    "broken": "The cited source record exists, but the underlying file cannot be opened.",
    "stale": "The cited source has changed since this answer was generated.",
    "recycled": "The cited graph source is currently in the recycle bin.",
    "unsupported": "This citation could not be matched to a current source used for the answer.",
}


def _resolve_stored_path(stored_path: str | None) -> Path | None:
    if not stored_path:
        return None

    direct = Path(stored_path)
    if direct.exists():
        return direct

    normalised = str(stored_path).replace("\\", "/")
    markers = (
        "evidence-data/",
        "/evidence-data/",
        "data/evidence/",
        "/data/evidence/",
        "ingestion/data/",
        "/ingestion/data/",
    )
    for marker in markers:
        marker_index = normalised.find(marker)
        if marker_index == -1:
            continue
        relative = normalised[marker_index + len(marker) :].lstrip("/")
        candidate = EVIDENCE_DATA_ROOT / PurePosixPath(relative)
        if candidate.exists():
            return candidate

    return direct


def _as_uuid(value: Any) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _normalise_page(value: Any) -> int | None:
    if value in (None, "", -1, "-1"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_hash(parts: list[Any]) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _content_sha256(text: str | None) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _case_filename_lookup(db: Session, case_id: uuid.UUID, filename: str | None) -> EvidenceFile | None:
    if not filename:
        return None
    return (
        db.execute(
            select(EvidenceFile)
            .where(
                EvidenceFile.case_id == case_id,
                func.lower(EvidenceFile.original_filename) == filename.lower(),
            )
            .order_by(EvidenceFile.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def _find_evidence(db: Session, case_id: uuid.UUID, source: dict[str, Any]) -> tuple[EvidenceFile | None, str | None]:
    mismatch_reason = None
    engine_job_id = source.get("engine_job_id")
    if engine_job_id:
        record = (
            db.execute(
                select(EvidenceFile)
                .where(EvidenceFile.engine_job_id == str(engine_job_id))
                .limit(1)
            )
            .scalars()
            .first()
        )
        if record:
            if record.case_id == case_id:
                return record, "engine_job_id"
            mismatch_reason = "engine_job_id belongs to a different case"

    evidence_id = _as_uuid(source.get("evidence_id") or source.get("doc_id"))
    if evidence_id:
        record = db.get(EvidenceFile, evidence_id)
        if record:
            if record.case_id == case_id:
                return record, "evidence_id"
            mismatch_reason = "evidence_id belongs to a different case"

    record = _case_filename_lookup(db, case_id, source.get("filename") or source.get("doc_name"))
    if record:
        return record, "filename"

    return None, mismatch_reason


def _is_recycled(db: Session, case_id: uuid.UUID, source: dict[str, Any]) -> bool:
    entity_key = source.get("entity_key") or source.get("key")
    if not entity_key:
        return False
    row = (
        db.execute(
            select(GraphRecycleBinItem.id)
            .where(
                GraphRecycleBinItem.case_id == case_id,
                GraphRecycleBinItem.original_key == str(entity_key),
                GraphRecycleBinItem.status.in_(["pending_delete", "active", "restoring"]),
            )
            .limit(1)
        )
        .first()
    )
    return row is not None


class CitationSnapshotService:
    citation_pattern = re.compile(r"\[[^\]]+\]\(doc://([^)\s]+)\)", re.IGNORECASE)

    def compute_source_id(self, source: dict[str, Any]) -> str:
        return "src_" + _source_hash(
            [
                source.get("chunk_id"),
                source.get("engine_job_id"),
                source.get("evidence_id") or source.get("doc_id"),
                source.get("filename"),
                source.get("page"),
                source.get("page_end"),
                source.get("content_sha256") or _content_sha256(source.get("excerpt")),
            ]
        )

    def normalize_sources(self, sources: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in sources or []:
            if not isinstance(raw, dict):
                continue
            filename = raw.get("filename") or raw.get("doc_name") or raw.get("name")
            excerpt = sanitize_text(str(raw.get("excerpt") or raw.get("text") or ""))
            source = {
                "source_id": raw.get("source_id"),
                "filename": str(filename) if filename else "Unknown",
                "page": _normalise_page(raw.get("page") or raw.get("page_start")),
                "page_end": _normalise_page(raw.get("page_end")),
                "excerpt": excerpt or None,
                "chunk_id": raw.get("chunk_id") or raw.get("id"),
                "doc_id": raw.get("doc_id"),
                "doc_name": raw.get("doc_name") or filename,
                "evidence_id": raw.get("evidence_id"),
                "engine_job_id": raw.get("engine_job_id"),
                "chunk_index": raw.get("chunk_index"),
                "start_char": raw.get("start_char"),
                "end_char": raw.get("end_char"),
                "content_sha256": raw.get("content_sha256") or _content_sha256(str(raw.get("text") or excerpt)),
                "evidence_sha256": raw.get("evidence_sha256") or raw.get("file_sha256") or raw.get("sha256"),
            }
            source["source_id"] = str(source["source_id"] or self.compute_source_id(source))
            if source["source_id"] in seen:
                continue
            seen.add(source["source_id"])
            normalized.append({k: v for k, v in source.items() if v is not None})
        return normalized

    def refresh_sources(
        self,
        db: Session,
        case_id: uuid.UUID,
        sources: list[dict[str, Any]] | None,
        snapshot_id: str | None = None,
    ) -> list[dict[str, Any]]:
        refreshed: list[dict[str, Any]] = []
        for source in self.normalize_sources(sources):
            enriched = dict(source)
            status = "deleted"
            reason = "No current evidence record matches this source."
            openable = False
            evidence, match_reason = _find_evidence(db, case_id, source)
            if match_reason and "different case" in match_reason:
                reason = match_reason

            if _is_recycled(db, case_id, source):
                status = "recycled"
                reason = "The graph entity backing this source is in the recycle bin."
            elif evidence:
                resolved = _resolve_stored_path(evidence.stored_path)
                openable = bool(resolved and resolved.exists())
                if not openable:
                    status = "broken"
                    reason = "The evidence row exists, but its stored file path is missing or inaccessible."
                elif source.get("evidence_sha256") and evidence.sha256 and source.get("evidence_sha256") != evidence.sha256:
                    status = "stale"
                    reason = "The stored source hash differs from the current evidence file hash."
                elif source.get("engine_job_id") and evidence.engine_job_id and source.get("engine_job_id") != evidence.engine_job_id:
                    status = "stale"
                    reason = "The citation points to a different processing job than the current evidence row."
                else:
                    status = "available"
                    reason = f"Matched current evidence by {match_reason or 'source metadata'}."

                enriched["evidence_id"] = str(evidence.id)
                enriched["current_engine_job_id"] = evidence.engine_job_id
                enriched["current_sha256"] = evidence.sha256

            enriched["status"] = status
            enriched["status_reason"] = reason
            enriched["openable"] = openable and status == "available"
            enriched["open_url"] = (
                f"/api/chat/citation-snapshots/{snapshot_id or '{snapshot_id}'}/sources/{enriched['source_id']}/file"
                if enriched["openable"]
                else None
            )
            enriched["warning"] = WARNING_BY_STATUS.get(status)
            refreshed.append(enriched)
        return refreshed

    def parse_answer_citations(self, answer: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        by_filename_page: dict[tuple[str, int | None], dict[str, Any]] = {}
        by_filename: dict[str, dict[str, Any]] = {}
        for source in sources:
            filename = str(source.get("filename") or "").lower()
            if not filename:
                continue
            by_filename.setdefault(filename, source)
            by_filename_page[(filename, _normalise_page(source.get("page")))] = source

        for index, match in enumerate(self.citation_pattern.finditer(answer or ""), start=1):
            target = unquote(match.group(1))
            filename, _, page_raw = target.rpartition("/")
            if not filename:
                filename = target
                page = None
            else:
                page = _normalise_page(page_raw)
            key = filename.lower()
            source = by_filename_page.get((key, page)) or by_filename.get(key)
            if source:
                citations.append(
                    {
                        "citation_id": f"cite_{index}",
                        "target": target,
                        "filename": filename,
                        "page": page,
                        "source_id": source["source_id"],
                        "status": source.get("status", "available"),
                        "unsupported": False,
                    }
                )
            else:
                citations.append(
                    {
                        "citation_id": f"cite_{index}",
                        "target": target,
                        "filename": filename,
                        "page": page,
                        "source_id": None,
                        "status": "unsupported",
                        "unsupported": True,
                        "warning": WARNING_BY_STATUS["unsupported"],
                    }
                )

        if not citations and (answer or "").strip():
            citations.append(
                {
                    "citation_id": "unsupported_no_citations",
                    "target": None,
                    "source_id": None,
                    "status": "unsupported",
                    "unsupported": True,
                    "warning": "No source citation was found in the answer.",
                }
            )
        return citations

    def create_snapshot(
        self,
        db: Session,
        *,
        case_id: uuid.UUID,
        case_revision_id: uuid.UUID | None,
        conversation_id: uuid.UUID | None,
        assistant_message_id: uuid.UUID | None,
        created_by_user_id: uuid.UUID | None,
        question: str,
        answer: str,
        model_provider: str | None,
        model_id: str | None,
        context_scope: str | None,
        selected_entity_keys: list[str] | None,
        citation_context: dict[str, Any] | None,
        sources: list[dict[str, Any]] | None,
    ) -> ChatCitationSnapshot:
        citation_context = citation_context or {}
        snapshot_id = uuid.uuid4()
        normalized_sources = self.refresh_sources(db, case_id, sources, snapshot_id=str(snapshot_id))
        snapshot = ChatCitationSnapshot(
            id=snapshot_id,
            case_id=case_id,
            case_revision_id=case_revision_id,
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
            created_by_user_id=created_by_user_id,
            question=sanitize_text(question or ""),
            answer=sanitize_text(answer or ""),
            model_provider=model_provider,
            model_id=model_id,
            context_scope=context_scope,
            selected_entity_keys=sanitize_json(selected_entity_keys) if selected_entity_keys else None,
            context_text=sanitize_text(citation_context.get("context") or ""),
            final_prompt=sanitize_text(citation_context.get("final_prompt") or ""),
            retrieval_payload=sanitize_json(citation_context.get("retrieval_payload") or {}),
            source_payload=sanitize_json(normalized_sources),
            answer_citations=sanitize_json(self.parse_answer_citations(answer, normalized_sources)),
        )
        db.add(snapshot)
        db.flush()
        return snapshot

    def get_snapshot_for_user(self, db: Session, snapshot_id: uuid.UUID, case_id: uuid.UUID | None = None) -> ChatCitationSnapshot:
        query = select(ChatCitationSnapshot).where(ChatCitationSnapshot.id == snapshot_id)
        if case_id:
            query = query.where(ChatCitationSnapshot.case_id == case_id)
        snapshot = db.execute(query).scalars().first()
        if not snapshot:
            raise HTTPException(status_code=404, detail="Citation snapshot not found")
        return snapshot

    def snapshot_payload(self, db: Session, snapshot: ChatCitationSnapshot) -> dict[str, Any]:
        sources = self.refresh_sources(db, snapshot.case_id, snapshot.source_payload, snapshot_id=str(snapshot.id))
        return {
            "id": str(snapshot.id),
            "case_id": str(snapshot.case_id),
            "case_revision_id": str(snapshot.case_revision_id) if snapshot.case_revision_id else None,
            "conversation_id": str(snapshot.conversation_id) if snapshot.conversation_id else None,
            "assistant_message_id": str(snapshot.assistant_message_id) if snapshot.assistant_message_id else None,
            "created_by_user_id": str(snapshot.created_by_user_id) if snapshot.created_by_user_id else None,
            "question": snapshot.question,
            "answer": snapshot.answer,
            "model_provider": snapshot.model_provider,
            "model_id": snapshot.model_id,
            "context_scope": snapshot.context_scope,
            "selected_entity_keys": snapshot.selected_entity_keys or [],
            "context_text": snapshot.context_text,
            "final_prompt": snapshot.final_prompt,
            "retrieval_payload": snapshot.retrieval_payload or {},
            "source_payload": sources,
            "answer_citations": self.parse_answer_citations(snapshot.answer, sources),
            "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        }

    def sources_for_snapshot_id(self, db: Session, snapshot_id: str | None) -> list[dict[str, Any]] | None:
        parsed = _as_uuid(snapshot_id)
        if not parsed:
            return None
        snapshot = db.get(ChatCitationSnapshot, parsed)
        if not snapshot:
            return None
        return self.refresh_sources(db, snapshot.case_id, snapshot.source_payload, snapshot_id=str(snapshot.id))

    def file_response(self, db: Session, snapshot: ChatCitationSnapshot, source_id: str) -> FileResponse:
        sources = self.refresh_sources(db, snapshot.case_id, snapshot.source_payload, snapshot_id=str(snapshot.id))
        source = next((item for item in sources if item.get("source_id") == source_id), None)
        if not source:
            raise HTTPException(status_code=404, detail="Citation source not found")
        if not source.get("openable"):
            raise HTTPException(status_code=409, detail=source.get("status_reason") or "Citation source is not openable")

        evidence_id = _as_uuid(source.get("evidence_id"))
        record = db.get(EvidenceFile, evidence_id) if evidence_id else None
        if not record or record.case_id != snapshot.case_id:
            raise HTTPException(status_code=404, detail="Evidence not found")

        file_path = _resolve_stored_path(record.stored_path)
        if not file_path or not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")

        filename = record.original_filename or source.get("filename") or "file"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=content_type,
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )


citation_snapshot_service = CitationSnapshotService()
