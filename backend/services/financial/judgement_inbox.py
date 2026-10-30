"""The lessons inbox: every correction of a judgement call, one line each, for the next lesson job to consume.

A correction proposes; a lesson job builds and measures; Neil releases. Nothing here changes a rule. Lines are
appended once per judgement (the judgement id is on the line); ``sync`` rewrites nothing, it adds what is missing.
"""
import fcntl
import json
import logging
import os
import re
import sys
from pathlib import Path

from sqlalchemy import select

log = logging.getLogger(__name__)
INBOX = Path(os.environ.get('LOUPE_FINANCIAL_JUDGEMENT_INBOX', '/mnt/owl-data/fin-wt/headless/JUDGEMENT-CORRECTIONS.md'))
HEADER = ('# Judgement corrections (lessons inbox)\n\n'
          'One line per correction a person made to a processor judgement call: rule | case | statement | '
          'before -> after | reason | link. A corrected rule gets a lesson row, built and measured the usual way.\n\n')


def _flat(text):
    return ' '.join(str(text or '').split()).replace('|', '/')


def line(item, statement=''):
    ev = item.get('evidence') or {}
    corr = ev.get('correction') or {}
    before = ev.get('before') if ev.get('before') is not None else (corr.get('before') or ev.get('chosen') or '')
    after = corr.get('after') if corr.get('after') is not None else ''
    link = (f"/cases/{item['case_id']}/financial?document={item.get('source_document_id') or ''}"
            f"&judgement={item['id']}")
    return (f"- {item.get('resolved_at') or ''} | {item['rule_id']} | case {item['case_id'][:8]} | "
            f"{_flat(statement) or (item.get('source_document_id') or '')[:8]} | {_flat(before)[:200]} -> "
            f"{_flat(after)[:200]} | {_flat(item.get('resolution_reason'))} | {link} | judgement {item['id']}\n")


def _statement(session, item):
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial import FinancialSourceDocument
    if not item.get('source_document_id'):
        return ''
    doc = session.get(FinancialSourceDocument, item['source_document_id'])
    file = session.get(EvidenceFile, doc.evidence_file_id) if doc is not None and doc.evidence_file_id else None
    return getattr(file, 'original_filename', '') or ''


def _known():
    try:
        return INBOX.read_text() if INBOX.exists() else ''
    except OSError:
        return ''


def append_correction(session, item):
    if item.get('status') != 'corrected':
        return False
    if f"judgement {item['id']}" in _known():
        return False
    text = line(item, _statement(session, item))
    # Two corrections at once (two workers, or two threads in one) must not both write the header or the same line:
    # the check and the write happen under one exclusive lock on the file, and the header goes in only when empty.
    with INBOX.open('a') as out:
        fcntl.flock(out.fileno(), fcntl.LOCK_EX)
        try:
            if f"judgement {item['id']}" in _known():
                return False
            if out.seek(0, os.SEEK_END) == 0:
                out.write(HEADER)
            out.write(text)
            out.flush()
        finally:
            fcntl.flock(out.fileno(), fcntl.LOCK_UN)
    return True


def missing(session):
    """Ids of corrections in the database with no line in the inbox (an append that failed and was not caught up)."""
    from postgres.models.financial_judgements import FinancialJudgement as J
    known = set(re.findall(r'judgement ([0-9a-f-]{36})', _known()))
    return [str(i) for i in session.scalars(select(J.id).where(J.status == 'corrected').order_by(J.resolved_at))
            if str(i) not in known]


def sync(session):
    """Append every correction not yet in the inbox (the periodic script). Returns the number appended."""
    from postgres.models.financial_judgements import FinancialJudgement as J
    from services.financial.judgements import as_dict
    added = 0
    for row in session.scalars(select(J).where(J.status == 'corrected').order_by(J.resolved_at)):
        added += append_correction(session, as_dict(row))
    return added


def check(session):
    """The watchdog's view of the inbox: sync, then report what is still missing and why (one JSON object)."""
    out = dict(inbox=str(INBOX), appended=0, error='')
    try:
        out['appended'] = sync(session)
    except Exception as exc:  # noqa: BLE001 - reported on the status board, not swallowed
        out['error'] = f'{type(exc).__name__}: {exc}'
    out['missing'] = missing(session)
    return out


if __name__ == '__main__':
    from postgres.session import _get_session_local
    with _get_session_local()() as db:
        if '--check' in sys.argv:
            print(json.dumps(check(db)))
        else:
            print('appended', sync(db))
