from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from fastapi import HTTPException
from services.transcript_review import is_audio, summary, ensure_source, feature_enabled

from postgres.models.evidence import EvidenceFile
from services import ai_budget, evidence_engine_client, evidence_signature, phone_files
from services.evidence_db_storage import EvidenceDBStorage
from services.evidence_job_sync import reconcile_case_jobs
from services.financial.admission_gate import gate_document_processing
from services.folder_context_service import build_processing_snapshot
from services.evidence_file_check import FILE_MISSING_DETAIL
from services.job_status_subscriber import get_subscriber

logger = logging.getLogger(__name__)


def _stored_path(stored_path: str | None) -> Path | None:
    """The path this module opens for a file, and the only one it opens.

    Given as a function so that :func:`gate_document_processing` can be handed
    the same one.  The gate decides whether a file is bank data the router
    holds back, and it has to decide that about the bytes this module is about
    to send; a gate resolving a path differently from its caller would clear
    one file and send another.

    ``routers.evidence._resolve_stored_path`` does more than this, falling back
    to a container layout when the stored path is not present on this host.  It
    returns the direct path unchanged whenever that path exists, and that is
    the only case reaching the gate -- everything else has already been counted
    as missing on disk and dropped -- so on the files a decision is actually
    taken about, the two agree exactly.

    The ``None`` branch is unreachable while ``evidence_files.stored_path`` is
    NOT NULL.  It is written anyway so that a schema which stopped being would
    skip the file rather than raise while building a path.
    """
    return Path(stored_path) if stored_path else None


def _serialize_profile_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        # Persist before uploading to the engine. Case refreshes may arrive
        # before the new engine job exists and must not resurrect an old run.
        "ingestion_request_id": snapshot.get("ingestion_request_id"),
        "execution_plan_id": snapshot.get("execution_plan_id"),
        "transcript_revision_id": snapshot.get("transcript_revision_id"),
        "preparation_mode": snapshot.get("preparation_mode", "full"),
        "source_folder_id": snapshot.get("source_folder_id"),
        "effective_context": snapshot.get("effective_context"),
        "effective_mandatory_instructions": snapshot.get("effective_mandatory_instructions") or [],
        "effective_special_entity_types": snapshot.get("effective_special_entity_types") or [],
        "chain": snapshot.get("chain") or [],
    }


def _financial_processing_files(db: Session, case_id: uuid.UUID, file_ids: list[uuid.UUID]):
    """Recheck the source choice atomically with the later processing handoff."""
    from postgres.models.case import Case
    from services.financial.file_visibility import require_financial_file
    db.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
    files = list(db.scalars(select(EvidenceFile).where(
        EvidenceFile.id.in_(file_ids)).order_by(EvidenceFile.id).with_for_update()
        .execution_options(populate_existing=True)))
    for file in files:
        if file.case_id != case_id:
            raise ValueError("Evidence file does not belong to this case")
        require_financial_file(file)
    return files


async def process_db_files(db: Session, *, case_id: uuid.UUID, file_ids: list[uuid.UUID], **options) -> dict[str, Any]:
    """Send evidence files to the engine, leaving out any file held from model reading and saying so. Every send to
    the engine passes here, so a held file reaches no model whichever route asked. A held file does not stop the rest
    of a selection: a phone folder's programs would otherwise refuse its documents. Financial reading asks for one
    named statement and waits for its reading, so there a held file is refused with the reason."""
    sendable, held = await run_in_threadpool(evidence_signature.split_held, db, case_id, file_ids, _stored_path)
    if held and options.get('preparation_mode') == 'pdf_review':
        from services.financial.pdf_candidates import PdfMappingError
        raise PdfMappingError(evidence_signature.held_words(len(held)), 409)
    if not held:
        return await _send_files(db, case_id=case_id, file_ids=file_ids, **options)
    await run_in_threadpool(db.commit)  # a signature read here for the first time stays read
    result = await _send_files(db, case_id=case_id, file_ids=sendable, **options) if sendable else dict(
        job_ids=[], file_count=0, skipped_count=0, message='No files sent')
    words = evidence_signature.held_words(len(held))
    return {**result, 'held_ids': [str(file_id) for file_id in held], 'skipped_count': result.get('skipped_count', 0) + len(held),
            'message': f"{result['message']}; {words}" if sendable else words}


async def _send_files(
    db: Session,
    *,
    case_id: uuid.UUID,
    file_ids: list[uuid.UUID],
    force_reprocess: bool = False,
    preparation_mode: str = "full",
    requested_by_user_id: uuid.UUID | None = None,
    audio_mode: str | None = None,
    _audio_resolved: bool = False,
    transcript_revisions: dict[str, str] | None = None,
    reviewed_ids: set[str] | None = None,
    execution_plan_id: str | None = None,
    processing_snapshots: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Send evidence files to the engine. The database work (selection, snapshots, the admission gate, marking the
    files, recording the jobs) runs in the thread pool on this session, in this order; only the engine calls and the
    job subscription are awaited on the event loop."""
    if preparation_mode not in ("full", "pdf_review", "audio_review"):
        raise ValueError("Unknown document preparation mode")
    if preparation_mode == "pdf_review":
        # Financial callers may retain the Case/Evidence locks from selecting
        # or restoring a reading, including an idempotent reprocessing request.
        # Persist that choice before the network wait. Visibility is checked
        # again under lock below before a processing request can be committed.
        await run_in_threadpool(db.commit)
    await reconcile_case_jobs(db, str(case_id))
    if (preparation_mode == 'audio_review' or audio_mode == 'review_first') and not feature_enabled():
        raise HTTPException(409, 'Transcript review is not enabled')
    if preparation_mode == 'full' and not _audio_resolved and audio_mode == 'review_first':
        full, preparations, deferred, recovered_job_ids = await run_in_threadpool(
            _partition_audio_files, db, case_id=case_id, file_ids=file_ids,
            force_reprocess=force_reprocess, audio_mode=audio_mode,
            reviewed_ids=reviewed_ids, execution_plan_id=execution_plan_id)
        results = []
        processing_count = 0
        if full:
            full_result = await process_db_files(db, case_id=case_id, file_ids=full,
                force_reprocess=force_reprocess, requested_by_user_id=requested_by_user_id,
                audio_mode=audio_mode, _audio_resolved=True, transcript_revisions=transcript_revisions,
                execution_plan_id=execution_plan_id, processing_snapshots=processing_snapshots)
            results.append(full_result)
            processing_count = full_result.get('file_count', 0)
        for file_id in preparations:
            results.append(await process_db_files(db, case_id=case_id, file_ids=[file_id],
                preparation_mode='audio_review', requested_by_user_id=requested_by_user_id,
                execution_plan_id=execution_plan_id, processing_snapshots=processing_snapshots))
        await run_in_threadpool(db.commit)
        return {'job_ids': recovered_job_ids + [job for result in results for job in result.get('job_ids', [])],
            'file_count': len(recovered_job_ids) + sum(result.get('file_count', 0) for result in results),
            'awaiting_review_ids': deferred, 'transcription_count': len(preparations),
            'processing_count': processing_count,
            'skipped_count': sum(result.get('skipped_count', 0) for result in results),
            'skipped_phone_files': sum(result.get('skipped_phone_files', 0) for result in results),
            'missing_on_disk': sum(result.get('missing_on_disk', 0) for result in results),
            'message': f'{processing_count} file(s) queued for processing; {len(preparations)} recording(s) queued for transcription; {len(deferred)} awaiting review'}
    ingestion_request_id = str(uuid.uuid4())

    # At a limit nothing is prepared or queued: the files stay as they are, with the reason in the refusal (HTTP 402).
    if preparation_mode != "pdf_review":  # PDF preparation reads the text layer and calls no model
        await run_in_threadpool(ai_budget.check, db, case_id, "processing these files")

    prepared = await run_in_threadpool(
        _prepare_files,
        db,
        case_id=case_id,
        file_ids=file_ids,
        force_reprocess=force_reprocess,
        preparation_mode=preparation_mode,
        requested_by_user_id=requested_by_user_id,
        ingestion_request_id=ingestion_request_id,
        audio_mode=audio_mode, transcript_revisions=transcript_revisions,
        execution_plan_id=execution_plan_id, processing_snapshots=processing_snapshots,
    )
    if isinstance(prepared, dict):
        return prepared
    file_tuples, per_file_metadata, valid_files, valid_ids, skipped_processing, missing_on_disk = prepared

    accepted_files: list[EvidenceFile] = []
    accepted_jobs: list[dict[str, Any]] = []
    refused: list[tuple[EvidenceFile, str]] = []
    recovered = False
    chunks = _send_chunks(per_file_metadata)
    for position, chunk in enumerate(chunks):
        try:
            done, refused_here = await _upload_isolating(case_id, file_tuples, per_file_metadata, chunk)
        except Exception as exc:
            # Not a refusal of particular files (the engine is unreachable, timed out or failed): the files of this
            # request may still have been accepted, so look for their jobs before calling anything failed.
            chunk_files = [valid_files[i] for i in chunk]
            found = await _recover_accepted(case_id, ingestion_request_id, [valid_ids[i] for i in chunk])
            if found is not None:
                accepted_files.extend(chunk_files)
                accepted_jobs.extend(found)
                recovered = True
                continue
            unsent = [valid_files[i] for later in chunks[position:] for i in later]
            await run_in_threadpool(_record_upload_failed, db, unsent, str(exc))
            if not accepted_files and not refused:
                raise  # nothing went: the caller reports the failure as before
            refused.extend((ef, str(exc)) for ef in unsent)
            break
        for index, job in done:
            accepted_files.append(valid_files[index])
            accepted_jobs.append(job)
        refused.extend((valid_files[index], reason) for index, reason in refused_here)
        for index, reason in refused_here:
            await run_in_threadpool(_record_upload_failed, db, [valid_files[index]], reason)

    if recovered:
        job_ids_out = await run_in_threadpool(_record_recovered_jobs, db, accepted_files, accepted_jobs)
        await reconcile_case_jobs(db, str(case_id))
        logger.warning("Recovered accepted jobs after upload response failure request_id=%s", ingestion_request_id)
    else:
        job_ids_out = await run_in_threadpool(_record_engine_jobs, db, accepted_files, accepted_jobs)

    if job_ids_out:
        subscriber = get_subscriber()
        await subscriber.track_jobs(job_ids_out, str(case_id))

    message = f"Processing {len(accepted_files)} file(s)"
    if refused:
        message += f"; {len(refused)} file(s) refused by the processing service, marked failed with the reason"
    if missing_on_disk:
        message += f"; {missing_on_disk} file(s) not sent: {FILE_MISSING_DETAIL}"
    return {
        "job_ids": job_ids_out,
        "file_count": len(accepted_files),
        "skipped_count": skipped_processing,
        "missing_on_disk": missing_on_disk,
        "message": message,
        **({"refused": [{"file_id": str(ef.id), "name": ef.original_filename, "reason": reason}
                        for ef, reason in refused]} if refused else {}),
        **({"recovered_after_response_error": True} if recovered else {}),
    }


# One request to the engine carries at most this many files and this much processing metadata. The engine's form
# parser refuses any field over 1 MiB (Starlette max_part_size) and so refuses the whole request; each file's metadata
# lists the other files of its folder, so 250 files of a 366-file folder sent 11.3 MB and all 250 failed (SB4,
# 28 Oct). The margin under 1 MiB covers the JSON separators between entries.
MAX_FILES_PER_SEND = 25
MAX_METADATA_BYTES_PER_SEND = 900_000


def _send_chunks(per_file_metadata: list[dict[str, Any]]) -> list[list[int]]:
    import json
    chunks: list[list[int]] = []
    current: list[int] = []
    size = 0
    for index, metadata in enumerate(per_file_metadata):
        item = len(json.dumps(metadata)) + 2
        if current and (len(current) >= MAX_FILES_PER_SEND or size + item > MAX_METADATA_BYTES_PER_SEND):
            chunks.append(current)
            current, size = [], 0
        current.append(index)
        size += item
    if current:
        chunks.append(current)
    return chunks


def _refusal_reason(exc: Exception) -> str | None:
    """The engine's own words when it refused the request for what was in it (a 4xx other than sign-in or rate
    limit, which say nothing about the files); None for any other failure."""
    import httpx
    if not isinstance(exc, httpx.HTTPStatusError):
        return None
    code = exc.response.status_code
    if code < 400 or code >= 500 or code in (401, 403, 404, 408, 429):
        return None
    try:
        detail = exc.response.json().get("detail")
    except Exception:
        detail = None
    detail = detail if isinstance(detail, str) and detail else exc.response.reason_phrase or str(code)
    return f"The processing service refused this file ({detail[:300]})"


async def _upload_isolating(case_id, file_tuples, per_file_metadata, indexes):
    """Send these files in one request. A refusal is split until each refused file is alone, so one bad file fails
    by itself with the engine's reason and the others are processed. Returns ([(index, job)], [(index, reason)])."""
    try:
        jobs = await evidence_engine_client.upload_file_paths_batch(
            case_id=str(case_id),
            files=[file_tuples[i] for i in indexes],
            processing_metadata=[per_file_metadata[i] for i in indexes],
        )
    except Exception as exc:
        reason = _refusal_reason(exc)
        if reason is None:
            raise
        if len(indexes) == 1:
            logger.warning("Engine refused one file: %s", reason)
            return [], [(indexes[0], reason)]
        middle = len(indexes) // 2
        left_done, left_refused = await _upload_isolating(case_id, file_tuples, per_file_metadata, indexes[:middle])
        right_done, right_refused = await _upload_isolating(case_id, file_tuples, per_file_metadata, indexes[middle:])
        return left_done + right_done, left_refused + right_refused
    return list(zip(indexes, jobs)), []


async def _recover_accepted(case_id, ingestion_request_id: str, file_ids: list[str]):
    """The engine's jobs for these files when it accepted them all before its response was lost, else None."""
    try:
        case_jobs = await evidence_engine_client.list_jobs(str(case_id))
    except Exception:
        logger.exception("Failed to check whether ingestion request %s was accepted", ingestion_request_id)
        return None
    jobs_by_source_id: dict[str, dict[str, Any]] = {}
    for job in case_jobs:
        if (job.get("pipeline_state") or {}).get("ingestion_request_id") != ingestion_request_id:
            continue
        source_id = str(job.get("source_evidence_file_id") or "")
        if source_id:
            jobs_by_source_id[source_id] = job
    found = [jobs_by_source_id[file_id] for file_id in file_ids if file_id in jobs_by_source_id]
    return found if len(found) == len(file_ids) else None


def _partition_audio_files(db, *, case_id, file_ids, force_reprocess, audio_mode,
                           reviewed_ids, execution_plan_id):
    chosen = EvidenceDBStorage.get_files_by_ids(db, file_ids)
    for file in chosen:
        if file.case_id != case_id:
            raise ValueError('Evidence file does not belong to this case')
    preparations, full, deferred, recovered_job_ids = [], [], [], []
    excluded_source_ids = set()
    for file in chosen:
        if (file.source_type in ('phone_extraction', 'phone_text')
            or not phone_files.external_processing_allowed(db, file)
            or phone_files.is_member_locator(file.stored_path)):
            full.append(file.id)  # The ordinary handoff reports the existing source-policy skip.
            excluded_source_ids.add(file.id)
            continue
        if execution_plan_id and (file.last_processed_profile_snapshot or {}).get('execution_plan_id') == execution_plan_id and file.engine_job_id:
            recovered_job_ids.append(str(file.engine_job_id))
            continue
        if file.status == 'processing' or (file.status == 'processed' and not force_reprocess):
            continue
        info = summary(file)
        reviewed = str(file.id) in reviewed_ids if reviewed_ids is not None else info.get('reviewed')
        if is_audio(file) and audio_mode == 'review_first' and not reviewed:
            if file.transcription or file.transcription_segments:
                ensure_source(db, file)
                deferred.append(str(file.id))
            else:
                preparations.append(file.id)
        else:
            full.append(file.id)
    # Apply the existing admission gate to the complete requested handoff
    # before any group starts. No audio choice bypasses a financial hold.
    eligible_ids = set(full + preparations) - excluded_source_ids
    candidates_for_gate = [f for f in chosen if f.id in eligible_ids]
    gate_document_processing(db, case_id=case_id, files=candidates_for_gate, resolve_path=_stored_path)
    # Legacy transcript adoption may have acquired the case audit lock.
    # Release it before a child group awaits the engine over HTTP.
    db.commit()
    return full, preparations, deferred, recovered_job_ids


def _prepare_files(
    db: Session,
    *,
    case_id: uuid.UUID,
    file_ids: list[uuid.UUID],
    force_reprocess: bool,
    preparation_mode: str,
    requested_by_user_id: uuid.UUID | None,
    ingestion_request_id: str,
    audio_mode: str | None = None,
    transcript_revisions: dict[str, str] | None = None,
    execution_plan_id: str | None = None,
    processing_snapshots: dict[str, dict] | None = None,
):
    """Select, snapshot, gate and mark the files to send, and commit. Returns the early result dict when nothing is
    sent, otherwise (file_tuples, per_file_metadata, valid_files, valid_ids, skipped_processing, missing_on_disk)."""
    if isinstance(db, Session):
        from services.financial.audit_chain import lock_case_audit_chain
        lock_case_audit_chain(db, case_id)
    if preparation_mode == "pdf_review":
        files = _financial_processing_files(db, case_id, file_ids)
    elif isinstance(db, Session):
        files = list(db.scalars(select(EvidenceFile).where(EvidenceFile.id.in_(file_ids))
            .order_by(EvidenceFile.id).with_for_update().execution_options(populate_existing=True)))
    else:
        files = EvidenceDBStorage.get_files_by_ids(db, file_ids)
    files_by_id = {f.id: f for f in files}

    candidates: list[EvidenceFile] = []
    skipped_processing = 0
    skipped_external = 0
    skipped_phone_reports = 0
    skipped_phone_texts = 0
    skipped_in_archive = 0
    missing_on_disk = 0
    recovered_job_ids = []

    for file_id in file_ids:
        ef = files_by_id.get(file_id)
        if ef is None:
            continue
        if str(ef.case_id) != str(case_id):
            raise ValueError("Evidence file does not belong to this case")
        if ef.source_type == "phone_extraction":
            # A phone report is read by its capture job when it is uploaded (01 section 4.4); a folder processed
            # as a whole, or a selection with ordinary files, leaves it out and says so.
            skipped_phone_reports += 1
            continue
        if ef.source_type == "phone_text":
            # A thread document is written from the phone's records (02 section 9.7); there is no file to process.
            skipped_phone_texts += 1
            continue
        if execution_plan_id and (ef.last_processed_profile_snapshot or {}).get('execution_plan_id') == execution_plan_id and ef.engine_job_id:
            recovered_job_ids.append(str(ef.engine_job_id))
            skipped_processing += 1
            continue
        reservation = (getattr(ef, 'metadata_', None) or {}).get('processing_reservation') or {}
        if reservation and reservation.get('plan_id') != execution_plan_id:
            from datetime import datetime, timezone
            if reservation.get('expires_at', '') > datetime.now(timezone.utc).isoformat():
                raise HTTPException(409, 'This file has already been reserved for another processing request.')
        if ef.status == "processing":
            skipped_processing += 1
            continue
        if not phone_files.external_processing_allowed(db, ef):
            # A phone file used in a dossier is never sent for processing (or embedding) without the case's
            # external-processing decision (07 section 6.4 item 4).
            skipped_external += 1
            continue
        if phone_files.is_member_locator(ef.stored_path):
            # Kept inside an uploaded archive and read there in place (cb-media item F): there is no path to send.
            skipped_in_archive += 1
            continue
        if ef.status == "processed" and not force_reprocess:
            skipped_processing += 1
            continue
        if is_audio(ef) and preparation_mode == 'full':
            info = summary(ef)
            if info.get('review_required') and not feature_enabled():
                raise HTTPException(409, 'Transcript review is disabled; saved revisions have been retained.')
            if audio_mode is None and (info.get('review_required') or (ef.metadata_ or {}).get('review_opted_in')) and not info.get('reviewed'):
                raise HTTPException(409, {'code': 'audio_review_choice_required',
                    'message': 'This recording is awaiting transcript review. Review it or explicitly choose Process without review.'})
        if preparation_mode == 'audio_review' and not is_audio(ef):
            raise HTTPException(422, 'Transcript review requires an audio recording')
        if preparation_mode == 'audio_review' and (ef.transcription or ef.transcription_segments):
            ensure_source(db, ef)
            skipped_processing += 1
            continue
        if preparation_mode == "pdf_review" and Path(ef.original_filename).suffix.lower() != ".pdf":
            raise ValueError("PDF review preparation accepts PDF files only")
        candidates.append(ef)

    if not candidates:
        message = "No eligible files to process"
        if skipped_external:
            message += (f"; {skipped_external} phone file(s) were not sent because this case has no decision "
                        "allowing phone material to be processed outside Loupe")
        if skipped_phone_reports:
            message += f"; {skipped_phone_reports} phone report(s) are read automatically when uploaded"
        if skipped_phone_texts:
            message += f"; {skipped_phone_texts} phone conversation text(s) are written from the phone's records"
        if skipped_in_archive:
            message += (f"; {skipped_in_archive} phone file(s) are kept inside an uploaded archive and read there, "
                        "so they are not sent for processing")
        return {
            "job_ids": recovered_job_ids,
            "file_count": len(recovered_job_ids),
            "skipped_count": (skipped_processing + skipped_external + skipped_phone_reports + skipped_phone_texts
                              + skipped_in_archive),
            "skipped_phone_files": skipped_external,
            "message": message,
        }

    file_tuples: list[tuple[str, Path, str]] = []
    per_file_metadata: list[dict[str, Any]] = []
    valid_files: list[EvidenceFile] = []

    for ef in candidates:
        path = _stored_path(ef.stored_path)
        if path is None or not path.exists():
            missing_on_disk += 1
            continue

        snapshot = (processing_snapshots or {}).get(str(ef.id)) or build_processing_snapshot(
            db,
            case_id=case_id,
            folder_id=ef.folder_id,
            file_id=ef.id,
        )
        snapshot = {
            **snapshot,
            "preparation_mode": preparation_mode,
            "ingestion_request_id": ingestion_request_id,
            "execution_plan_id": execution_plan_id,
            "requested_by_user_id": str(requested_by_user_id) if requested_by_user_id else None,
            "source_evidence_file_id": str(ef.id),
        }
        if preparation_mode == "pdf_review":
            reading_mode = (ef.metadata_ or {}).get("statement_pdf_reading_mode", "automatic")
            if reading_mode not in ("automatic", "page_images"):
                raise ValueError("Unknown PDF reading method")
            snapshot["pdf_reading_mode"] = reading_mode

        file_tuples.append(
            (
                ef.original_filename,
                path,
                _guess_content_type(ef.original_filename),
            )
        )
        per_file_metadata.append(snapshot)
        valid_files.append(ef)

    if not valid_files:
        return {
            "job_ids": [],
            "file_count": 0,
            "skipped_count": skipped_processing,
            "missing_on_disk": missing_on_disk,
            "message": f"{missing_on_disk} file(s) not sent: {FILE_MISSING_DETAIL}" if missing_on_disk else "No files found on disk",
        }

    # Nothing above this line has changed anything.  The gate is the last thing
    # asked before the first thing is written, so a refusal leaves the files
    # exactly as it found them: not marked processing, no snapshot, no job.
    #
    # It is applied to `valid_files` and not to `file_ids`, because a file that
    # is not going to be sent needs no decision behind it.  Gating the request
    # instead of the send would turn today's "that one is missing from disk, we
    # skipped it" into a refusal of the whole batch over a file nobody was
    # about to process.
    #
    # Raises `UnadmittedFileError`, which the three routes that reach here turn
    # into a 409 naming each held file and what the router found in it.  It is
    # deliberately not caught: a gate whose failure can be swallowed by the
    # caller it constrains is not a gate.
    gate_document_processing(
        db,
        case_id=case_id,
        files=valid_files,
        resolve_path=_stored_path,
    )

    for ef, snapshot in zip(valid_files, per_file_metadata):
        if execution_plan_id and (ef.metadata_ or {}).get('processing_reservation', {}).get('plan_id') == execution_plan_id:
            metadata = dict(ef.metadata_ or {})
            metadata.pop('processing_reservation', None)
            ef.metadata_ = metadata
        if is_audio(ef):
            if preparation_mode == 'audio_review':
                ef.metadata_ = {**(ef.metadata_ or {}), 'review_opted_in': True}
            elif feature_enabled():
                state = ensure_source(db, ef)
                if state:
                    snapshot['transcript_revision_id'] = (transcript_revisions or {}).get(str(ef.id)) or str(state.working_revision_id)

    EvidenceDBStorage.mark_processing(
        db,
        [ef.id for ef in valid_files],
        force=force_reprocess,
    )
    for ef, snapshot in zip(valid_files, per_file_metadata):
        EvidenceDBStorage.set_processing_snapshot(
            db,
            ef.id,
            profile_snapshot=_serialize_profile_snapshot(snapshot),
            folder_id=ef.folder_id,
        )
    valid_ids = [str(ef.id) for ef in valid_files]  # read before the commit expires the rows
    db.commit()
    skipped = skipped_processing + skipped_external + skipped_phone_reports + skipped_phone_texts + skipped_in_archive
    return file_tuples, per_file_metadata, valid_files, valid_ids, skipped, missing_on_disk


def _record_recovered_jobs(db: Session, valid_files: list[EvidenceFile], recovered_jobs: list[dict[str, Any]]) -> list[str]:
    recovered_job_ids: list[str] = []
    for ef, job in zip(valid_files, recovered_jobs):
        ef.engine_job_id = str(job["id"])
        ef.status = "processing"
        ef.last_error = None
        recovered_job_ids.append(str(job["id"]))
    db.commit()
    return recovered_job_ids


def _record_upload_failed(db: Session, valid_files: list[EvidenceFile], error: str) -> None:
    EvidenceDBStorage.mark_processed(
        db,
        [ef.id for ef in valid_files],
        error=error,
    )
    db.commit()


def _record_engine_jobs(db: Session, valid_files: list[EvidenceFile], jobs: list[dict[str, Any]]) -> list[str]:
    job_ids_out: list[str] = []
    for ef, job in zip(valid_files, jobs):
        ef.engine_job_id = str(job["id"])
        job_ids_out.append(str(job["id"]))
    db.commit()
    return job_ids_out


def _guess_content_type(file_name: str) -> str:
    import mimetypes

    return mimetypes.guess_type(file_name)[0] or "application/octet-stream"
