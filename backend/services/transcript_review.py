"""Revisioned transcript editing. Shared with the evidence engine via /backend.

All writers lock the EvidenceFile row before touching transcript state. Machine
output never contains investigator overrides; jobs refer to immutable revisions.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile
from postgres.models.transcript import TranscriptSource, TranscriptRevision, TranscriptState, TranscriptReview

RENDERER_VERSION = 'speaker-transcript-v1'
MAPS = ('text_overrides', 'turn_speaker_overrides', 'speakers', 'speaker_merges', 'speaker_entity_ids')


def feature_enabled():
    return os.getenv('AUDIO_TRANSCRIPT_REVIEW_ENABLED', '0').lower() in ('1', 'true', 'yes', 'on')


def is_audio(file):
    from services.audio_media import SUPPORTED_AUDIO_EXTENSIONS
    mime = mimetypes.guess_type(file.original_filename)[0] or ''
    return Path(file.original_filename).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS or mime.startswith('audio/')


def summary(file):
    return dict((getattr(file, 'metadata_', None) or {}).get('transcript_review') or {})


def _lock(db, file):
    from services.financial.audit_chain import lock_case_audit_chain
    lock_case_audit_chain(db, file.case_id)
    # Production sessions disable autoflush. Persist this transaction's pointer
    # changes before populate_existing reads them back under the source lock.
    db.flush()
    latest_metadata = db.scalar(select(EvidenceFile.metadata_).where(EvidenceFile.id == file.id).with_for_update())
    file.metadata_ = deepcopy(latest_metadata or {})
    # Refresh state after obtaining the file lock, including when another writer
    # committed while this session was waiting for the lock.
    return db.scalar(select(TranscriptState).where(TranscriptState.evidence_file_id == file.id)
                     .execution_options(populate_existing=True))


def _hash(source, payload):
    return hashlib.sha256(json.dumps([RENDERER_VERSION, str(source.id), source.source_sha256,
        payload], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _revision(db, file, source, payload, actor=None, parent=None):
    revision = TranscriptRevision(evidence_file_id=file.id, case_id=file.case_id, source_id=source.id,
        payload=deepcopy(payload), digest=_hash(source, payload), author_id=actor, parent_id=parent)
    db.add(revision); db.flush()
    return revision


def refresh_summary(db, file, state):
    if state is None:
        return {}
    current = db.get(TranscriptRevision, state.working_revision_id)
    reviewed = state.reviewed_revision_id == state.working_revision_id
    published = state.published_revision_id == state.working_revision_id
    previously_processed = bool(state.published_revision_id or getattr(file, 'processed_at', None) or file.status == 'processed')
    unchanged_legacy = previously_processed and state.published_revision_id is None and current.parent_id is None
    value = {'revision_id': str(state.working_revision_id), 'source_id': str(state.source_id),
        'reviewed': reviewed, 'review_required': state.review_required,
        'review_state': 'processed' if published or unchanged_legacy else 'ready' if reviewed else 'awaiting_review',
        'changed_since_processing': bool(previously_processed and not published and (state.published_revision_id or current.parent_id)),
        'published_revision_id': str(state.published_revision_id) if state.published_revision_id else None,
        'digest': current.digest}
    file.metadata_ = {**(file.metadata_ or {}), 'transcript_review': value}
    db.flush()
    return value


def capture_source(db, file, *, job_id, text, segments, review_required=False, metadata=None):
    state = _lock(db, file)
    existing = db.scalar(select(TranscriptSource).where(TranscriptSource.engine_job_id == str(job_id)))
    if existing:
        return state
    if state:
        # Reading a saved transcript again is never an implicit retranscription.
        return state
    source = TranscriptSource(evidence_file_id=file.id, case_id=file.case_id, engine_job_id=str(job_id),
        source_sha256=file.sha256, text=text or '', segments=deepcopy(segments or []), metadata_=metadata or {})
    db.add(source); db.flush()
    payload = {key: {} for key in MAPS}
    payload['speakers'] = dict(file.transcription_speakers or {})
    payload['speaker_merges'] = dict(file.transcription_speaker_merges or {})
    revision = _revision(db, file, source, payload)
    state = TranscriptState(evidence_file_id=file.id, case_id=file.case_id, source_id=source.id,
        working_revision_id=revision.id, review_required=review_required)
    db.add(state)
    file.transcription = text or ''
    file.transcription_segments = deepcopy(segments or [])
    refresh_summary(db, file, state)
    return state


def ensure_source(db, file):
    state = _lock(db, file)
    if state is None and (file.transcription or file.transcription_segments):
        state = capture_source(db, file, job_id=f'legacy:{file.id}', text=file.transcription,
            segments=file.transcription_segments)
    return state


def canonical_speaker(speaker, merges):
    seen = set()
    while speaker in merges:
        if speaker in seen:
            raise HTTPException(422, 'Speaker merges cannot contain a cycle')
        seen.add(speaker); speaker = merges[speaker]
    return speaker


def effective_segments(source, payload):
    result = []
    for index, original in enumerate(source.segments):
        segment = deepcopy(original)
        segment['id'] = str(segment.get('id') or f'turn-{index}')
        segment['text'] = payload['text_overrides'].get(segment['id'], segment.get('text', ''))
        segment['speaker'] = payload['turn_speaker_overrides'].get(segment['id'], segment.get('speaker') or 'unknown')
        result.append(segment)
    return result


def read_transcript(db, file):
    state = ensure_source(db, file)
    if state is None:
        raise HTTPException(409, {'code': 'transcript_unavailable', 'message': 'Transcribe this recording first.'})
    source = db.get(TranscriptSource, state.source_id)
    revision = db.get(TranscriptRevision, state.working_revision_id)
    return {**refresh_summary(db, file, state), 'evidence_id': str(file.id), 'case_id': str(file.case_id), 'evidence_status': file.status,
        'original_text': source.text, 'original_segments': source.segments,
        'transcription': revision.payload.get('body_text', source.text),
        'segments': effective_segments(source, revision.payload), 'speakers': revision.payload['speakers'],
        'speaker_merges': revision.payload['speaker_merges'], 'speaker_entity_ids': revision.payload['speaker_entity_ids'],
        'payload': revision.payload, 'version': state.version}


def save_draft(db, file, expected_revision_id, changes, actor):
    if len(json.dumps(changes, ensure_ascii=False)) > 2_000_000:
        raise HTTPException(422, 'This edit exceeds the transcript revision size limit. The saved transcript has been retained.')
    state = ensure_source(db, file)
    if state is None:
        raise HTTPException(409, 'Transcribe this recording first')
    source = db.get(TranscriptSource, state.source_id)
    current = db.get(TranscriptRevision, state.working_revision_id)
    stale = str(state.working_revision_id) != str(expected_revision_id)
    old = db.get(TranscriptRevision, uuid.UUID(str(expected_revision_id))) if stale else current
    conflict = HTTPException(409, {'code': 'transcript_changed', 'message': 'Another edit was saved. Reload before saving.',
                                  'revision_id': str(state.working_revision_id)})
    if old is None or old.evidence_file_id != file.id or old.source_id != state.source_id:
        raise conflict
    payload = deepcopy(old.payload)
    if '_validated_entity_labels' in changes:
        payload['entity_labels'] = changes['_validated_entity_labels']
    if changes.get('restore_original'):
        payload['text_overrides'] = {}
        payload['turn_speaker_overrides'] = {}
        payload.pop('body_text', None)
    for key in MAPS:
        if key not in changes or changes[key] is None:
            continue
        if key in ('text_overrides', 'turn_speaker_overrides'):
            for item, value in changes[key].items():
                if value is None: payload[key].pop(str(item), None)
                else: payload[key][str(item)] = str(value)
        else:
            payload[key] = {str(k).strip(): str(v).strip() for k, v in changes[key].items() if v}
    if 'body_text' in changes:
        if changes['body_text'] is None: payload.pop('body_text', None)
        else: payload['body_text'] = changes['body_text']
    ids = {str(segment.get('id') or f'turn-{i}') for i, segment in enumerate(source.segments)}
    if any(set(payload[key]) - ids for key in ('text_overrides', 'turn_speaker_overrides')):
        raise HTTPException(422, 'Unknown transcript turn')
    speakers = {str(s.get('speaker') or 'unknown') for s in source.segments}
    speakers.update(payload['turn_speaker_overrides'].values())
    if len(speakers | set(payload['speakers'])) > 64:
        raise HTTPException(422, 'Too many speakers')
    if any(len(name) > 80 for name in payload['speakers'].values()):
        raise HTTPException(422, 'Speaker names must be 80 characters or fewer')
    if set(payload['speakers']) - speakers or set(payload['speaker_entity_ids']) - speakers:
        raise HTTPException(422, 'Unknown transcript speaker')
    merges = {k: v for k, v in payload['speaker_merges'].items() if k != v}
    if (set(merges) | set(merges.values())) - speakers:
        raise HTTPException(422, 'Unknown merge speaker')
    payload['speaker_merges'] = {k: canonical_speaker(k, merges) for k in merges}
    groups = {}
    for speaker, entity_id in payload['speaker_entity_ids'].items():
        target = canonical_speaker(speaker, merges)
        if target in groups and groups[target] != entity_id:
            raise HTTPException(422, 'Merged speakers have different linked entities. Choose one identity first.')
        groups[target] = entity_id
    payload['speaker_entity_ids'] = groups
    if stale:
        if current.parent_id == old.id and current.author_id == actor and current.payload == payload:
            return read_transcript(db, file)  # Retry after a lost save response.
        raise conflict
    if payload != old.payload:
        revision = _revision(db, file, source, payload, actor, old.id)
        state.working_revision_id = revision.id
        state.version += 1
        state.review_required = True
        file.transcription_speakers = dict(payload['speakers'])
        file.transcription_speaker_merges = dict(payload['speaker_merges'])
    return read_transcript(db, file)


def approve_revision(db, file, revision_id, actor, request_key):
    state = ensure_source(db, file)
    receipt = db.scalar(select(TranscriptReview).where(TranscriptReview.evidence_file_id == file.id,
        TranscriptReview.request_key == request_key))
    if receipt and (str(receipt.revision_id) != str(revision_id) or receipt.actor_id != actor):
        raise HTTPException(409, 'Review request key was already used for different input')
    if state is None or str(state.working_revision_id) != str(revision_id):
        raise HTTPException(409, {'code': 'transcript_changed', 'message': 'Save and review the current transcript.'})
    if receipt is None:
        db.add(TranscriptReview(evidence_file_id=file.id, case_id=file.case_id, revision_id=state.working_revision_id,
            actor_id=actor, request_key=request_key))
    state.reviewed_revision_id = state.working_revision_id
    state.review_required = True
    return read_transcript(db, file)


def render_revision(source, revision):
    """Canonical text plus spans; generated speaker labels are separate from speech."""
    segments = effective_segments(source, revision.payload)
    text, spans = '', []
    fallback = {}
    speaker_names = revision.payload['speakers']
    duplicates = {name for name in speaker_names.values() if list(speaker_names.values()).count(name) > 1}
    for turn in segments:
        speaker = canonical_speaker(turn['speaker'], revision.payload['speaker_merges'])
        if speaker not in fallback: fallback[speaker] = f'Speaker {len(fallback) + 1}'
        name = revision.payload['speakers'].get(speaker) or revision.payload.get('entity_labels', {}).get(
            revision.payload['speaker_entity_ids'].get(speaker)) or fallback[speaker]
        prefix = f"[{float(turn.get('start') or 0):.3f}–{float(turn.get('end') or 0):.3f}] "
        header = prefix + name + (f' (speaker {speaker})' if name in duplicates else '') + '\n'
        start = len(text)
        text += header + turn['text'] + '\n\n'
        spans.append({'segment_id': turn['id'], 'speaker': speaker, 'speaker_name': name,
            'entity_id': revision.payload['speaker_entity_ids'].get(speaker), 'start_char': start,
            'label_start_char': start + len(prefix),
            'speech_start_char': start + len(header), 'end_char': len(text) - 2,
            'start_seconds': turn.get('start', 0), 'end_seconds': turn.get('end', 0)})
    if not segments: text = revision.payload.get('body_text', source.text)
    return {'text': text, 'segments': segments, 'metadata': {'file_type': 'audio',
        'transcript_revision_id': str(revision.id), 'transcript_digest': revision.digest,
        'transcript_renderer': RENDERER_VERSION, 'transcript_turns': spans}}
