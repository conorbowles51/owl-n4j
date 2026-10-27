"""The lessons inbox: every correction of a judgement call, one line each, for the next lesson job to consume.

A correction proposes; a lesson job builds and measures; Neil releases. Nothing here changes a rule. Lines are
appended once per judgement (the judgement id is on the line); ``sync`` rewrites nothing, it adds what is missing.
"""
import logging
import os
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
    known = _known()
    if f"judgement {item['id']}" in known:
        return False
    with INBOX.open('a') as out:
        if not known:
            out.write(HEADER)
        out.write(line(item, _statement(session, item)))
    return True


def sync(session):
    """Append every correction not yet in the inbox (the periodic script). Returns the number appended."""
    from postgres.models.financial_judgements import FinancialJudgement as J
    from services.financial.judgements import as_dict
    added = 0
    for row in session.scalars(select(J).where(J.status == 'corrected').order_by(J.resolved_at)):
        added += append_correction(session, as_dict(row))
    return added


if __name__ == '__main__':
    from postgres.session import _get_session_local
    with _get_session_local()() as db:
        print('appended', sync(db))
