"""Fresh source-bound native arithmetic for correction review and its audit."""
import hashlib
import os
import stat
from datetime import date

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.enums import TransactionDirection
from services.financial.money import Money
from services.financial.native import CenturyWindow, NativeError, read_native
from services.financial.bai2 import Bai2Error
from services.financial.camt053 import Camt053Error
from services.financial.mt940 import Mt940Error
from services.financial.nacha import NachaError
from services.financial.native_recheck import NativeAmountReading, recheck_native_controls

MAX_NATIVE_RECHECK_BYTES = 16 * 1024 * 1024


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _source_bytes(stored_path, expected, resolve_path):
    try:
        path = resolve_path(stored_path)
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_NATIVE_RECHECK_BYTES:
                raise ValueError('Native source must be a regular file of at most16 MiB.')
            data = stream.read(MAX_NATIVE_RECHECK_BYTES + 1)
            after = os.fstat(stream.fileno())
        if (len(data) != before.st_size or _signature(before) != _signature(after)
                or _signature(after) != _signature(os.stat(path))):
            raise ValueError('Native source changed during reading.')
    except (OSError, TypeError) as exc:
        raise ValueError('Native source bytes are unavailable.') from exc
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Native source bytes differ from the retained evidence digest.')
    return data


def correction_native_controls(session, document, rows, *, transaction_id,
                               amount_minor, direction, resolve_path):
    """Return current/proposed controls, or an explicit unavailable reason.

    Historical originals bind parsed rows; current replacements override only
    amount and direction. This does not promote proof class or change evidence.
    """
    if document.extraction_layer != 0:
        return None
    try:
        if resolve_path is None:
            raise ValueError('Native source storage is not available to this calculation.')
        if len(rows) > 2000:
            raise ValueError('Native control review exceeds the2000-reading history limit.')
        if any(r.case_id != document.case_id or r.source_document_id != document.id for r in rows):
            raise ValueError('Native rows have inconsistent source ownership.')
        originals = [r for r in rows if not (r.provenance or {}).get('correction')]
        current = [r for r in rows if not r.superseded_by_id and r.ledger_status != 'superseded']
        if not originals or len(originals) > 1000:
            raise ValueError('Native control review requires1–1000 original source readings.')
        if len({r.row_index for r in originals}) != len(originals) or len({r.row_index for r in current}) != len(current):
            raise ValueError('Native source row indices are duplicated.')
        dates = [r.ordering_date for r in originals]
        if any(not isinstance(d, date) for d in dates):
            raise ValueError('Recorded native date context is missing.')
        window = CenturyWindow(min(dates), max(dates))
        file = session.scalar(select(EvidenceFile).where(
            EvidenceFile.id == document.evidence_file_id,
            EvidenceFile.case_id == document.case_id).with_for_update(read=True))
        if file is None or file.sha256 != document.sha256_at_ingestion:
            raise ValueError('Native source identity differs from ingestion.')
        data = _source_bytes(file.stored_path, file.sha256, resolve_path)
        native = read_native(data, window=window, default_currency=document.currency)
        expected = dict(zip((r.row_index for r in native.rows), native.content_hashes()))
        if expected != {r.row_index: r.content_hash for r in originals}:
            raise ValueError('Fresh native parsing does not match every retained original reading.')
        old = {r.row_index: r for r in originals}
        if set(old) != {r.row_index for r in current} or any(
                r.account_id != old[r.row_index].account_id or r.currency != old[r.row_index].currency
                for r in current):
            raise ValueError('Current native row population or account ownership differs from the source.')
        target = next((r for r in current if r.id == transaction_id), None)
        if target is None:
            raise ValueError('The corrected native row is not current.')
        readings = {r.row_index: NativeAmountReading(
            Money.from_minor_units(r.amount_minor, r.currency), TransactionDirection(r.direction)) for r in current}
        proposed = {**readings, target.row_index: NativeAmountReading(
            Money.from_minor_units(amount_minor, target.currency), TransactionDirection(direction))}
        return dict(available=True, sha256=file.sha256,
            parser_name=native.parser_name, parser_version=native.parser_version,
            date_context=dict(earliest=window.earliest.isoformat(), latest=window.latest.isoformat(),
                              basis='Recorded original ledger ordering dates; complete original content hashes must match.'),
            current=recheck_native_controls(native, readings),
            proposed=recheck_native_controls(native, proposed),
            current_transaction_ids=[str(r.id) for r in sorted(current, key=lambda r: r.row_index)],
            limitation='Conditional arithmetic on verified original bytes and current readings. Source interpretation and proof class are not approved by these checks.')
    except (ValueError, NativeError, Bai2Error, Camt053Error, Mt940Error, NachaError) as exc:
        return dict(available=False, reason=str(exc))
