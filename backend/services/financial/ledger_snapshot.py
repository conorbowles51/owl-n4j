"""Deterministic immutable content for an unfinished ledger export.

Captures rows, source classification and totals from the same bounded SELECT.
This is not an externally exposed export: decision history and an export-event
manifest must be captured before that workflow is complete.
"""
import hashlib
import json
from dataclasses import dataclass
from services.financial.ledger_summary import ledger_summary, LedgerSummaryError


@dataclass(frozen=True)
class LedgerSnapshot:
    content: str
    sha256: str
    byte_count: int


def capture_ledger_snapshot(session, *, case_id, account_id=None, start_date=None, end_date=None):
    result=ledger_summary(session,case_id=case_id,account_id=account_id,start_date=start_date,
        end_date=end_date,capture_readings=True)
    if not result['available']:
        raise LedgerSummaryError(result['reason'])
    document=dict(schema='loupe.financial.ledger_snapshot/1',ledger=result,
        export_ready=False,limitations=['Decision history has not been captured. This is an internal snapshot, not a completed export.',
            'Source digests are recorded ingestion digests; source bytes were not reverified for this snapshot.'])
    # No generation time in the content: equal captured inputs yield equal bytes.
    content=json.dumps(document,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    encoded=content.encode('utf-8')
    return LedgerSnapshot(content=content,sha256=hashlib.sha256(encoded).hexdigest(),byte_count=len(encoded))
