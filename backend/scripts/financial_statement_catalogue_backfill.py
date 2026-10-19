"""Store each multi-statement file's catalogue once on its saved periods (dry run by default).

Saved periods written before services.financial.statement_catalogue each carry
their file's whole statement catalogue in ``statement_import_original``. This
script rewrites them to the current form: the period keeps its own choice, the
catalogue is kept once per file and digest, and the reading as read stays
provable (``statement_import_original_full_sha256`` = the digest it was saved
with).

Every record is checked before it is changed: its stored reading must match
its recorded digest, and rejoining the compacted reading with the catalogue
must reproduce that digest exactly. A record failing either check is reported
and left unchanged.

Without ``--apply`` the transaction is READ ONLY and nothing is written; the
report gives counts and bytes only (no names, numbers or amounts). ``--apply``
is a live write: run it only on Neil's decision, when no import is running
(each changed record gets a new integrity digest, so a detail edit opened
before the run asks to be reloaded; each update is recorded by the audit
trigger).

    python3 scripts/financial_statement_catalogue_backfill.py [--case UUID] [--apply]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def _size(value):
    return len(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


def plan(session, case_id=None):
    """(changes, report). changes: [(source id, new metadata)]."""
    from sqlalchemy import select
    from postgres.models.financial import FinancialSourceDocument as Source
    from services.financial.pdf_candidates import _digest
    from services.financial.statement_catalogue import (CATALOGUE, CATALOGUE_SHA256, FULL_SHA256,
                                                        compact_original)
    report = defaultdict(int)
    meta = Source.metadata_
    # Candidates are found without loading any reading: only records whose
    # catalogue lists more than one statement and that have no reference yet.
    query = select(Source.id).where(meta['statement_import_original'].is_not(None),
                                    meta[CATALOGUE_SHA256].as_string().is_(None))
    if case_id is not None:
        query = query.where(Source.case_id == case_id)
    holders = {}
    for case, file_id, digest in session.execute(select(Source.case_id, Source.evidence_file_id,
            meta[CATALOGUE]['sha256'].as_string()).where(meta[CATALOGUE]['sha256'].as_string().is_not(None))):
        holders[(case, file_id, digest)] = True
    changes = []
    for source_id in session.scalars(query.order_by(Source.id)):
        document = session.get(Source, source_id)
        metadata = document.metadata_ or {}
        original = metadata.get('statement_import_original')
        report['records_examined'] += 1
        stored, catalogue = compact_original(original, metadata.get('statement_import_statement_id'))
        if catalogue is None:
            report['records_single_statement'] += 1
            session.expunge(document)
            continue
        if _digest(original) != metadata.get('statement_import_original_sha256'):
            report['records_unverified_left_unchanged'] += 1
            session.expunge(document)
            continue
        rejoined = dict(stored, statement_choices=catalogue)
        if _digest(rejoined) != metadata['statement_import_original_sha256']:
            report['records_not_reproducible_left_unchanged'] += 1
            session.expunge(document)
            continue
        digest = _digest(catalogue)
        new = dict(metadata, statement_import_original=stored, statement_import_original_sha256=_digest(stored))
        new[CATALOGUE_SHA256] = digest
        new[FULL_SHA256] = metadata['statement_import_original_sha256']
        key = (document.case_id, document.evidence_file_id, digest)
        if key not in holders:
            holders[key] = True
            new[CATALOGUE] = dict(sha256=digest, choices=catalogue)
            report['catalogues_kept_once'] += 1
        report['records_compacted'] += 1
        report['bytes_before'] += _size(metadata)
        report['bytes_after'] += _size(new)
        changes.append((source_id, new))
        session.expunge(document)
    report['files_with_catalogue'] = len({(c, f) for c, f, _ in holders})
    return changes, dict(report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--case', help='limit to one case id')
    parser.add_argument('--apply', action='store_true', help='write the changes (live write; Neil decides)')
    args = parser.parse_args(argv)
    from uuid import UUID
    from postgres.session import _get_session_local
    case_id = UUID(args.case) if args.case else None
    with _get_session_local()() as session:
        if not args.apply:
            sys.path.insert(0, str(BACKEND / 'scripts'))
            from financial_reader_recovery_estimate import read_only
            read_only(session)
        changes, report = plan(session, case_id)
        if args.apply:
            from postgres.models.financial import FinancialSourceDocument as Source
            for source_id, metadata in changes:
                document = session.get(Source, source_id)
                document.metadata_ = metadata
                session.flush()
                session.expunge(document)
            session.commit()
            report['applied'] = True
        else:
            session.rollback()
            report['applied'] = False
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
