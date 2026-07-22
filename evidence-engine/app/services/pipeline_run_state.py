from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any


TERMINAL_STAGES = {"completed", "failed"}


def build_extraction_quality_report(
    *,
    entities: list[Any],
    relationships: list[Any],
    chunk_count: int,
    document_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic, model-independent ingestion quality signals."""
    metadata = document_metadata or {}
    fact_records = [
        fact
        for entity in entities
        for fact in (getattr(entity, "verified_facts", None) or [])
        if isinstance(fact, dict)
    ]
    total_records = len(entities) + len(relationships) + len(fact_records)
    grounded_records = sum(
        bool(getattr(entity, "source_location", None)) for entity in entities
    )
    grounded_records += sum(
        bool(getattr(relationship, "source_location", None))
        for relationship in relationships
    )
    grounded_records += sum(bool(fact.get("source_location")) for fact in fact_records)
    coverage = round(grounded_records / total_records, 4) if total_records else 1.0

    low_confidence_pages = int(
        metadata.get(
            "low_confidence_page_count",
            metadata.get("ocr_low_confidence_pages", 0),
        )
        or 0
    )
    warnings: list[str] = []
    if grounded_records < total_records:
        warnings.append("ungrounded_records")
    if low_confidence_pages:
        warnings.append("low_confidence_ocr")
    summary_status = metadata.get("document_summary_status")
    if summary_status == "failed":
        warnings.append("document_summary_failed")
    if not entities and chunk_count:
        warnings.append("no_entities_extracted")

    return {
        "version": 1,
        "status": "warning" if warnings else "passed",
        "chunk_count": chunk_count,
        "entity_count": len(entities),
        "relationship_count": len(relationships),
        "verified_fact_count": len(fact_records),
        "grounding": {
            "grounded_records": grounded_records,
            "total_records": total_records,
            "coverage": coverage,
        },
        "ocr": {
            "page_count": int(metadata.get("page_count", 0) or 0),
            "low_confidence_pages": low_confidence_pages,
            "extraction_mode": metadata.get("extraction_mode"),
        },
        "document_summary": {
            "status": summary_status or "unknown",
            "error": metadata.get("document_summary_error"),
        },
        "warnings": warnings,
    }


def add_verification_quality(
    report: dict[str, Any],
    verification: dict[str, int],
) -> dict[str, Any]:
    enriched = deepcopy(report)
    enriched["claim_verification"] = dict(verification)
    if any(
        verification.get(key, 0)
        for key in ("rejected_claim_count", "uncertain_claim_count", "unreviewed_claim_count")
    ):
        warnings = list(enriched.get("warnings") or [])
        if "claims_quarantined_or_unreviewed" not in warnings:
            warnings.append("claims_quarantined_or_unreviewed")
        enriched["warnings"] = warnings
        enriched["status"] = "warning"
    return enriched


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _finish_attempt(
    attempt: dict[str, Any],
    *,
    status: str,
    now: datetime,
    error: str | None = None,
) -> None:
    if attempt.get("status") != "running":
        return
    attempt["status"] = status
    attempt["completed_at"] = _timestamp(now)
    started_at = datetime.fromisoformat(str(attempt["started_at"]).replace("Z", "+00:00"))
    attempt["duration_ms"] = max(0, round((now - started_at).total_seconds() * 1000))
    if error:
        attempt["error"] = error


def transition_pipeline_state(
    current: dict[str, Any] | None,
    *,
    stage: str,
    message: str = "",
    error: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return an updated durable stage-attempt record for one pipeline run."""
    observed_at = now or datetime.now(UTC)
    state = deepcopy(current or {})
    state.setdefault("version", 1)
    state.setdefault("stages", {})

    previous_stage = state.get("current_stage")
    if stage in TERMINAL_STAGES:
        previous = state["stages"].get(previous_stage or "", {})
        attempts = previous.get("attempts") or []
        if attempts:
            _finish_attempt(
                attempts[-1],
                status="failed" if stage == "failed" else "completed",
                now=observed_at,
                error=error,
            )
        state["current_stage"] = stage
    elif previous_stage != stage:
        previous = state["stages"].get(previous_stage or "", {})
        previous_attempts = previous.get("attempts") or []
        if previous_attempts:
            _finish_attempt(previous_attempts[-1], status="completed", now=observed_at)

        stage_state = state["stages"].setdefault(
            stage,
            {"attempt_count": 0, "attempts": []},
        )
        stage_state["attempt_count"] = int(stage_state.get("attempt_count", 0)) + 1
        stage_state["attempts"].append(
            {
                "attempt": stage_state["attempt_count"],
                "status": "running",
                "started_at": _timestamp(observed_at),
                "message": message,
            }
        )
        state["current_stage"] = stage
    else:
        attempts = state["stages"].get(stage, {}).get("attempts") or []
        if attempts and message:
            attempts[-1]["message"] = message

    state["updated_at"] = _timestamp(observed_at)
    state["last_message"] = message
    if error:
        state["last_error"] = error
    elif stage not in TERMINAL_STAGES:
        state.pop("last_error", None)
    return state


def transition_chunk_publication(
    current: dict[str, Any] | None,
    *,
    publication_state: str,
    evidence_file_id: str | None = None,
    revision_id: str | None = None,
    file_name: str | None = None,
    error: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Update the job-embedded transactional outbox for chunk publication."""
    if publication_state not in {"staged", "ready", "publishing", "retry", "published"}:
        raise ValueError(f"Unsupported chunk publication state: {publication_state}")

    observed_at = now or datetime.now(UTC)
    state = deepcopy(current or {})
    publication = dict(state.get("chunk_publication") or {})
    if publication_state == "staged":
        if not evidence_file_id or not revision_id or not file_name:
            raise ValueError("Staged chunk publication requires document identity and revision")
        publication = {
            "state": "staged",
            "evidence_file_id": evidence_file_id,
            "revision_id": revision_id,
            "file_name": file_name,
            "attempt_count": 0,
            "staged_at": _timestamp(observed_at),
        }
    else:
        if not publication:
            raise ValueError("Chunk publication must be staged before it can transition")
        publication["state"] = publication_state
        if publication_state == "ready":
            publication["ready_at"] = _timestamp(observed_at)
        elif publication_state == "publishing":
            publication["attempt_count"] = int(publication.get("attempt_count", 0)) + 1
            publication["last_attempt_at"] = _timestamp(observed_at)
        elif publication_state == "published":
            publication["published_at"] = _timestamp(observed_at)
            publication.pop("last_error", None)

    if error:
        publication["last_error"] = error
    publication["updated_at"] = _timestamp(observed_at)
    state["chunk_publication"] = publication
    state["updated_at"] = _timestamp(observed_at)
    return state


def transition_batch_dispatch(
    current: dict[str, Any] | None,
    *,
    dispatch_state: str,
    batch_id: str | None = None,
    case_id: str | None = None,
    error: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Update the durable outbox used to submit an ingestion batch to ARQ."""
    if dispatch_state not in {"ready", "dispatching", "retry", "dispatched"}:
        raise ValueError(f"Unsupported batch dispatch state: {dispatch_state}")

    observed_at = now or datetime.now(UTC)
    state = deepcopy(current or {})
    dispatch = dict(state.get("batch_dispatch") or {})
    if not dispatch:
        if dispatch_state != "ready" or not batch_id or not case_id:
            raise ValueError("A batch dispatch must start ready with batch and case IDs")
        dispatch = {
            "state": "ready",
            "batch_id": batch_id,
            "case_id": case_id,
            "queue_job_id": f"evidence-batch:{batch_id}",
            "attempt_count": 0,
            "ready_at": _timestamp(observed_at),
        }
    else:
        dispatch["state"] = dispatch_state
        if dispatch_state == "dispatching":
            dispatch["attempt_count"] = int(dispatch.get("attempt_count", 0)) + 1
            dispatch["last_attempt_at"] = _timestamp(observed_at)
        elif dispatch_state == "dispatched":
            dispatch["dispatched_at"] = _timestamp(observed_at)
            dispatch.pop("last_error", None)

    if error:
        dispatch["last_error"] = error
    dispatch["updated_at"] = _timestamp(observed_at)
    state["batch_dispatch"] = dispatch
    state["updated_at"] = _timestamp(observed_at)
    return state
