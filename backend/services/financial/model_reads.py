"""Load names a model read (one JSON object per line) through the model origin: each is saved as the model's
reading with its citation, shown as "Read by Claude · not confirmed" until a person confirms it.

A line: {"case": <uuid>, "payment_id": <uuid>, "value": <name>, "page": <n>, "file": <name>, "why": <text>,
"model": "Claude", "model_id": "...", "for": <person's name>, "for_email": <address>, "for_user_id": <uuid>}.
``case``, ``payment_id``, ``value`` and ``for`` are required; the rest is the citation and who did it.

Each line goes through the payment label path (services.financial.payment_labels.update_payment_labels) with a
model actor, so a person's name or link is never replaced (the line is refused and reported), and the label
history keeps the reading. Lines that were saved, or name a payment that already carries that name (reported
as unchanged), are removed from the file; refused or broken lines stay in it
with nothing changed, and the report says why.

    python -m services.financial.model_reads <file.jsonl> [--apply]
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid

REQUIRED = ('case', 'payment_id', 'value', 'for')


def load_model_reads(session, lines, *, apply=False):
    """Save each reading through the label path as the model's. Returns (results, lines to keep)."""
    from postgres.models.financial import FinancialTransaction
    from services.financial.model_work import ModelWorkError, model_actor
    from services.financial.payment_labels import PaymentLabelsError, PaymentLabelsRequest, update_payment_labels
    results, keep = [], []
    for number, raw in enumerate(lines, 1):
        text = raw.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
            missing = [key for key in REQUIRED if not str(item.get(key) or '').strip()]
            if missing:
                raise ValueError('missing ' + ', '.join(missing))
            case_id, payment_id = uuid.UUID(str(item['case'])), uuid.UUID(str(item['payment_id']))
            row = session.get(FinancialTransaction, payment_id)
            if row is None or row.case_id != case_id:
                raise ValueError('payment not found in that case')
            actor = model_actor(for_name=item['for'], for_email=item.get('for_email') or 'unknown@model.local',
                                for_user_id=item.get('for_user_id'), model=item.get('model') or 'Claude',
                                model_id=item.get('model_id') or '',
                                citation=dict(page=item.get('page'), file=item.get('file'),
                                              source_document_id=str(row.source_document_id)),
                                how=item.get('why') or '')
            version = (row.metadata_ or {}).get('investigation_labels', {}).get('version', 0)
            request = PaymentLabelsRequest(transactions=[dict(id=payment_id, version=version)],
                                           counterparty_name=str(item['value']))
            if apply:
                outcome = update_payment_labels(session, case_id=case_id, request=request, actor=actor,
                                                reason=item.get('why') or None)
            else:
                # Same path, nothing kept: the precedence checks run and the session is rolled back.
                outcome = update_payment_labels(session, case_id=case_id, request=request, actor=actor,
                                                reason=item.get('why') or None, commit=False)
                session.rollback()
            # The payment already carries this name: nothing is recorded, and the report says so.
            status = ('saved' if apply else 'would_save') if outcome.get('changed') else 'unchanged'
            results.append(dict(line=number, payment_id=str(payment_id), value=item['value'], status=status))
            if not apply:
                keep.append(raw)
        except (PaymentLabelsError, ModelWorkError, ValueError, TypeError) as exc:
            session.rollback()
            results.append(dict(line=number, status='refused', reason=str(exc)))
            keep.append(raw)
    return results, keep


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('file')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    with open(args.file, encoding='utf-8') as handle:
        lines = handle.readlines()
    from postgres.session import _get_session_local
    with _get_session_local()() as session:
        results, keep = load_model_reads(session, lines, apply=args.apply)
    if args.apply:
        with open(args.file, 'w', encoding='utf-8') as handle:
            handle.writelines(line if line.endswith('\n') else line + '\n' for line in keep)
    json.dump(dict(results=results, kept=len(keep), applied=args.apply), sys.stdout, indent=2)
    print()


if __name__ == '__main__':
    main()
