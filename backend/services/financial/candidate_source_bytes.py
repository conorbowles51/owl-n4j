"""Verify a saved candidate's source bytes without changing its original snapshot.

This is a point-in-time prerequisite for the future materialization writer, not
an admission permit. That writer must hold source/review locks through rebinding,
this check and its commit. A successful digest check establishes neither the
accuracy of the extraction nor the financial meaning of the selected rows.
"""
import hashlib
import os
import stat
from datetime import datetime, timezone

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from services.financial.candidate_assessment import current_candidate_original
from services.financial.candidate_store import CandidateStoreError


MAX_SOURCE_BYTES = 256 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def verify_candidate_source_bytes(session, *, case_id, candidate_id, resolve_path):
    """Rebind a candidate, then hash its case-scoped stored file in bounded chunks.

The resolver is the application's trusted storage resolver, never a request path.
No file is opened for an unknown/cross-case candidate or a stale source binding.
The caller owns the transaction; this function never flushes, commits or rolls
back. Database locks cannot prevent external filesystem changes after this read.
"""
    with session.no_autoflush:
        saved, _candidate, bound = current_candidate_original(
            session, case_id=case_id, candidate_id=candidate_id,
        )
        row = session.execute(select(EvidenceFile.stored_path, EvidenceFile.sha256)
            .where(EvidenceFile.id == bound.proposal.evidence_file_id,
                   EvidenceFile.case_id == case_id).with_for_update(read=True)).one_or_none()
        if row is None:
            raise CandidateStoreError("Source file not found in this case.", 404)
        stored_path, expected = row
        if expected != bound.file_sha256:
            raise CandidateStoreError("Source digest changed since candidate binding. Reload it.")
        try:
            path = resolve_path(stored_path)
            if path is None:
                raise OSError("Unavailable source")
            # NONBLOCK prevents a mistakenly stored FIFO from hanging before
            # fstat can refuse it. Only ordinary files are hashed.
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise CandidateStoreError("Source storage is not a regular file.")
                if before.st_size > MAX_SOURCE_BYTES:
                    raise CandidateStoreError("Source exceeds the 256 MiB verification limit.", 422)
                digest, count = hashlib.sha256(), 0
                while chunk := stream.read(_CHUNK_BYTES):
                    count += len(chunk)
                    if count > MAX_SOURCE_BYTES:
                        raise CandidateStoreError("Source exceeds the 256 MiB verification limit.", 422)
                    digest.update(chunk)
                after = os.fstat(stream.fileno())
                if _signature(before) != _signature(after) or count != before.st_size:
                    raise CandidateStoreError("Source file changed during verification. Retry after it is stable.")
        except (OSError, ValueError) as exc:
            if isinstance(exc, CandidateStoreError):
                raise
            # Do not disclose internal paths, operating-system errors or bytes.
            raise CandidateStoreError("Source file is unavailable for byte verification.") from exc
        if digest.hexdigest() != expected:
            raise CandidateStoreError("Source bytes do not match the saved evidence digest.")
    return dict(case_id=str(case_id), candidate_id=str(candidate_id),
        evidence_file_id=str(bound.proposal.evidence_file_id), mapping_id=saved["id"],
        mapping_revision=saved["mapping_revision"], sha256=expected, byte_count=count,
        verified_at=datetime.now(timezone.utc).isoformat(), file_bytes_verified=True,
        applied=False, limitation="Bytes matched at verification time; extraction accuracy and ledger admission are not established.")
