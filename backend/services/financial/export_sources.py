"""Fresh, bounded bytes for the same-case source files referenced by an export."""
import hashlib
import os
import re
import stat
from pathlib import Path
from uuid import UUID
from postgres.models.evidence import EvidenceFile
from services.financial.ledger_summary import LedgerSummaryError

MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_FILES = 100


def capture_export_sources(session, snapshot, *, case_id, resolve_path):
    expected = {}
    for reading in snapshot['ledger']['readings']:
        source = reading['source']
        file_id, digest = source['evidence_file_id'], source['sha256_at_ingestion']
        if not file_id or not isinstance(digest, str) or re.fullmatch(r'[a-f0-9]{64}', digest) is None:
            raise LedgerSummaryError('A captured source has no registered file or valid ingestion digest; source files were not bundled.')
        if file_id in expected and expected[file_id] != digest:
            raise LedgerSummaryError('Conflicting ingestion digests for one source file; source files were not bundled.')
        expected[file_id] = digest
    if len(expected) > MAX_SOURCE_FILES:
        raise LedgerSummaryError('More than 100 source files; narrow the export scope. No partial source bundle was produced.')
    result = []
    remaining = MAX_SOURCE_BYTES
    for file_id, digest in sorted(expected.items()):
        evidence = session.get(EvidenceFile, UUID(file_id))
        if evidence is None or evidence.case_id != case_id or evidence.sha256 != digest:
            raise LedgerSummaryError('Source ownership or its recorded digest changed; source files were not bundled.')
        path = resolve_path(evidence.stored_path)
        if path is None:
            raise LedgerSummaryError('A registered source file is unavailable; source files were not bundled.')
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise LedgerSummaryError('A registered source is not a regular file; source files were not bundled.')
                if info.st_size > remaining:
                    raise LedgerSummaryError('Source files exceed 64 MiB; narrow the export scope. No partial source bundle was produced.')
                content = stream.read(remaining + 1)
        except OSError as exc:
            raise LedgerSummaryError('A registered source file could not be read; source files were not bundled.') from exc
        if len(content) > remaining:
            raise LedgerSummaryError('Source files exceed 64 MiB; no partial source bundle was produced.')
        actual = hashlib.sha256(content).hexdigest()
        if actual != digest:
            raise LedgerSummaryError('Source bytes no longer match the ingestion digest; source files were not bundled.')
        remaining -= len(content)
        suffix = Path(evidence.original_filename or '').suffix.lower()
        if not re.fullmatch(r'\.[a-z0-9]{1,10}', suffix):
            suffix = '.bin'
        result.append(dict(evidence_file_id=file_id, filename=evidence.original_filename,
            archive_path=f'source-files/{file_id}{suffix}', sha256=actual, byte_count=len(content), content=content))
    return tuple(result)
