"""Layout learning, from the command line (services/financial/layout_learning.py).

  examples FILE_ID ...        read (or reuse) every page image of each file, list the proved examples
  dump DIR [--shard I N]      the stored text (table sources) of every file with table geometry, all cases, one
                              pickle per file in DIR (only files not dumped yet): the corpus the gates read
  gates PROFILE.json --corpus DIR [--truth T] [--inventory I] [--off NAME ...] [--json OUT]
                              both data gates for a draft: every corpus file whose profile pick changes is read
                              without and with it (0 lost / 0 changed), and those with tier-A truth are judged
                              (0 wrong / 0 lost / 0 double); exit 0 only when both pass
  learn [--fingerprint F] [--file FILE_ID ...] [--out DIR]
                              the loop for the reader-gap register's layouts (or the named files): examples,
                              draft, test; writes each draft and its test to DIR (default: the learning state)

The database is read in a READ ONLY transaction; nothing is written to a statement, a review, a batch or an
account. Page images go only through the vision reader's approved provider path and cost rules.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text  # noqa: E402


def _session():
    from postgres.session import _get_session_local
    db = _get_session_local()()
    db.execute(text('SET TRANSACTION READ ONLY'))
    return db


def file_pages(path):
    import fitz
    with fitz.open(str(path)) as document:
        return list(range(1, document.page_count + 1))


def examples(db, file_ids, budget, out=print):
    from postgres.models.evidence import EvidenceFile
    from services.financial import layout_learning as ll
    found, spent = [], 0.0
    for file_id in file_ids:
        file = db.get(EvidenceFile, file_id)
        pages = file_pages(file.stored_path)
        if len(pages) > ll.vr.MAX_PAGES:
            out('%s %s: %s pages, more than the %s read from page images' % (file_id[:8], file.original_filename,
                                                                            len(pages), ll.vr.MAX_PAGES))
            continue
        try:
            reading, cost = ll.read_file_images(db, file.case_id, file, pages, budget=budget - spent,
                                                resolve_path=Path)
        except ll.NotProved as reason:
            out('%s %s: not read: %s' % (file_id[:8], file.original_filename, reason))
            continue
        spent += cost
        for example, reason in ll.examples_of(reading, pages):
            if example:
                example = dict(example, file_id=str(file_id), case_id=str(file.case_id), filename=file.original_filename)
                found.append(example)
                out('%s %s: PROVED %s %s..%s open %s close %s rows %s %s' % (
                    file_id[:8], file.original_filename, example['account_number'], example['period_start'],
                    example['period_end'], example['opening_minor'], example['closing_minor'], len(example['rows']),
                    example['convention']))
            else:
                out('%s %s: not proved: %s' % (file_id[:8], file.original_filename, reason))
        out('   cost %.4f (%s)' % (cost, reading.get('reused') or ('stored' if not cost else 'read')))
    return found, spent


def dump(db, directory, shard=0, shards=1, out=print):
    import os
    import pickle
    from postgres.models.evidence import EvidenceTableGeometry
    from services.financial.candidate_sources import read_candidate_source
    os.makedirs(directory, exist_ok=True)
    from datetime import datetime, timezone
    files = sorted(db.execute(text(
        'SELECT g.evidence_file_id, f.case_id, max(g.extracted_at) FROM %s g JOIN evidence_files f ON f.id = '
        'g.evidence_file_id GROUP BY g.evidence_file_id, f.case_id' % EvidenceTableGeometry.__tablename__)).all(),
        key=lambda r: str(r[0]))[shard::shards]
    done = 0
    errors = {}
    for file_id, case_id, extracted in files:
        path = Path(directory, '%s.pkl' % file_id)
        if path.exists():
            try:
                stored = pickle.loads(path.read_bytes())
            except Exception:  # noqa: BLE001 - an unreadable pickle is dumped again
                stored = {}
            if stored.get('extracted_at') == str(extracted):
                continue  # unchanged since it was dumped
        try:
            pages = [(g.page_number, len(g.payload or [])) for g in db.scalars(
                select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == file_id)
                .order_by(EvidenceTableGeometry.page_number))]
            sources = [read_candidate_source(db, case_id=case_id, evidence_file_id=file_id, page_number=page,
                                             table_index=index) for page, tables in pages for index in range(tables)]
            temporary = path.with_suffix('.tmp')
            temporary.write_bytes(pickle.dumps(dict(case_id=str(case_id), sources=sources, extracted_at=str(extracted))))
            os.replace(temporary, path)
            done += 1
        except Exception as error:
            errors[str(file_id)] = '%s: %s' % (type(error).__name__, str(error)[:200])
            out('ERR %s %s' % (file_id, errors[str(file_id)]))
            db.rollback()
            db.execute(text('SET TRANSACTION READ ONLY'))
    if shards == 1:
        # The gates read only a complete, fresh corpus (manifest_problem).
        Path(directory, 'manifest.json').write_text(json.dumps(dict(
            dumped_at=datetime.now(timezone.utc).isoformat(), expected=len(files), errors=errors), indent=1))
    out('dumped %s, errors %s, of %s files' % (done, len(errors), len(files)))


# The corpus the gates read: dumped completely within this many hours.
CORPUS_MAX_AGE_HOURS = 24
# Errors allowed in a corpus: stored tables the candidate-source reader refuses, which the router cannot read
# either, with or without any profile.
UNREADABLE_EITHER_WAY = ('PdfMappingError',)


def manifest_problem(directory, now=None):
    """None when the corpus is complete and fresh, else why the gates must not trust it."""
    from datetime import datetime, timezone
    path = Path(directory, 'manifest.json')
    if not path.exists():
        return 'The corpus has no manifest (dump it completely first).'
    manifest = json.loads(path.read_text())
    now = now or datetime.now(timezone.utc)
    age = (now - datetime.fromisoformat(manifest['dumped_at'])).total_seconds() / 3600
    if age > CORPUS_MAX_AGE_HOURS:
        return 'The corpus was dumped %.0f hours ago (more than %s).' % (age, CORPUS_MAX_AGE_HOURS)
    present = len(list(Path(directory).glob('*.pkl')))
    errors = manifest.get('errors') or {}
    if present + len(errors) < manifest['expected']:
        return 'The corpus holds %s of %s files.' % (present + len(errors), manifest['expected'])
    other = [f for f, e in errors.items() if not e.startswith(UNREADABLE_EITHER_WAY)]
    if other:
        return '%s files of the corpus could not be dumped (%s).' % (len(other), errors[other[0]][:120])
    return None


def corpus(directory):
    import pickle
    for path in sorted(Path(directory).glob('*.pkl')):
        stored = pickle.loads(path.read_bytes())
        yield path.stem, stored['case_id'], stored['sources']


def run_gates(profile, directory, truth, inventory, off=(), out=print):
    import pickle
    from services.financial import layout_learning as ll, statement_engine_profiles as sep
    problem = manifest_problem(directory)
    if problem:
        out('corpus: %s -> FAIL' % problem)
        return dict(passed=False, corpus=dict(passed=False, reason=problem, files=0, unchanged=0, rematched=[],
                                             lost=[], changed=[], gained=[], doubled=[], served_changed=[]),
                    truth=dict(passed=False, judged=[], wrong=[], lost=[], double=[], reason='corpus not trusted'))
    saved_off = set(sep.PROFILES_OFF)
    sep.PROFILES_OFF.update(off)
    try:
        result = ll.gates(profile, corpus(directory),
                      lambda file_id: pickle.loads(Path(directory, '%s.pkl' % file_id).read_bytes())['sources'],
                          truth, json.loads(Path(inventory).read_text()), out=out)
    finally:
        sep.PROFILES_OFF.clear()
        sep.PROFILES_OFF.update(saved_off)
    c, t = result['corpus'], result['truth']
    out('corpus: %s files, %s pick unchanged, %s re-read: lost %s changed %s doubled %s served-changed %s gained %s'
        ' -> %s' % (c['files'], c['unchanged'], len(c['rematched']), len(c['lost']), len(c['changed']),
                    len(c['doubled']), len(c['served_changed']), len(c['gained']), 'PASS' if c['passed'] else 'FAIL'))
    out('truth: %s truth documents, %s files judged: wrong %s lost %s double %s -> %s%s' % (
        t.get('truth_documents'), len(t['judged']), len(t['wrong']), len(t['lost']), len(t['double']),
        'PASS' if t['passed'] else 'FAIL', (' (%s)' % t['reason']) if t.get('reason') else ''))
    return result


def register_layouts(fingerprints=None, held_only=True):
    """{fingerprint: [statement entries]} from the reader-gap register (fin-holes B, reader_gaps.register_path)."""
    from services.financial import reader_gaps
    data = reader_gaps.read_register()
    found = {}
    for entry in data['statements'].values():
        mark = entry.get('fingerprint') or 'unknown'
        if fingerprints and mark not in fingerprints:
            continue
        found.setdefault(mark, []).append(entry)
    if held_only:
        found = {m: es for m, es in found.items() if any(not e.get('resolved_at') for e in es)}
    return found


def learn_layout(db, mark, entries, directory, *, provider=None, model=None, drafter='derived', draft_provider=None,
                 draft_model=None, truth=None, inventory=None, gate=True, out=print):
    """The loop for one layout: examples from page images, a draft, the exact re-read test, the gates.
    Returns the layout's learning record (also kept in the learning state)."""
    import pickle
    import time
    from postgres.models.evidence import EvidenceFile
    from services.financial import layout_learning as ll
    started = time.monotonic()
    ll.set_layout(mark, state='learning', files=len({e['file_id'] for e in entries}),
                  banks=sorted({e.get('bank') or '' for e in entries} - {''}))
    files, reasons, spent, image_seconds, provider_errors = [], [], 0.0, 0.0, 0
    # Already read: every file of the layout has a period the text reader proves today (a written profile or the
    # plain reader). Nothing to learn; the register's entry resolves on its next sweep.
    readers = {}
    for file_id in sorted({e['file_id'] for e in entries}):
        path = Path(directory, '%s.pkl' % file_id)
        if path.exists():
            reading, used = ll.text_reading(pickle.loads(path.read_bytes())['sources'])
            readers[file_id] = used if any((s.get('engine') or {}).get('proved') for s in reading) else None
    if readers and all(readers.values()):
        names = sorted(set(readers.values()))
        return ll.set_layout(mark, state='read', reason='The text reader already proves every statement of this '
                             'layout (%s).' % ', '.join(n for n in names), readers=readers)
    requested = 0
    for file_id in sorted({e['file_id'] for e in entries}):
        if requested >= ll.MAX_EXAMPLE_FILES:
            reasons.append('%s: not read; %s files of this layout were read from page images already'
                           % (file_id[:8], ll.MAX_EXAMPLE_FILES))
            continue
        file = db.get(EvidenceFile, file_id)
        if file is None:
            reasons.append('%s: the file is no longer stored' % file_id[:8])
            continue
        pages = file_pages(file.stored_path)
        if len(pages) > ll.vr.MAX_PAGES:
            reasons.append('%s: %s pages, more than the %s read from page images' % (file_id[:8], len(pages), ll.vr.MAX_PAGES))
            continue
        try:
            reading, cost = ll.read_file_images(db, file.case_id, file, pages, budget=ll.LAYOUT_BUDGET_USD - spent,
                                                resolve_path=Path, provider=provider, model=model)
        except ll.NotProved as error:
            reasons.append('%s: not read from its page images: %s' % (file_id[:8], str(error)[:200]))
            continue
        except Exception as error:  # noqa: BLE001 - the provider failed: recorded, the layout is tried again later
            provider_errors += 1
            spent += getattr(error, 'reserved', 0.0)  # counted against the layout's budget (it may be billed)
            reasons.append('%s: the page-image request failed: %s' % (file_id[:8], str(error)[:200]))
            continue
        spent += cost
        requested += 1 if cost else 0
        image_seconds += reading.get('seconds') or 0
        examples = []
        for example, reason in ll.examples_of(reading, pages):
            if example:
                examples.append(example)
            else:
                reasons.append('%s: %s' % (file_id[:8], reason))
        path = Path(directory, '%s.pkl' % file_id)
        if not path.exists():
            dump(db, directory, out=lambda m: None)  # only missing files are read
        sources = pickle.loads(path.read_bytes())['sources'] if path.exists() else []
        files.append(dict(file_id=file_id, case_id=str(file.case_id), sources=sources, lines=ll.text_lines(sources),
                          examples=examples, filename=file.original_filename))
    proved = [f for f in files if f['examples']]
    record = dict(examples_proved=sum(len(f['examples']) for f in files), example_files=len(proved),
                  example_reasons=reasons, cost_usd=round(spent, 4), image_seconds=round(image_seconds, 1),
                  example_model=model or 'workload')
    if not proved:
        reason = 'No statement of this layout was proved by its page images (%s).' % ('; '.join(reasons[:4]) or 'none read')
        out('%s: %s' % (mark, reason))
        # Waiting (not failed) when a page-image request failed: those files were never judged.
        return ll.set_layout(mark, state='unread' if provider_errors else 'draft_failed', reason=reason, **record)
    if not all(f['sources'] for f in proved):
        reason = 'The stored text of %s is not available.' % ', '.join(f['file_id'][:8] for f in proved if not f['sources'])
        return ll.set_layout(mark, state='draft_failed', reason=reason, **record)
    name = 'learned-%s' % mark
    phrases = {fid: set(v) for fid, v in phrase_index(directory).items()}
    if drafter == 'llm' and not all(ll.vr.approved(f['case_id']) for f in proved):
        reason = 'The statements\' text may not be sent to a drafting model (case not approved for page images).'
        return ll.set_layout(mark, state='draft_failed', reason=reason, **record)
    if drafter == 'llm':
        from services.ai_provider_credentials import get_provider_api_key
        profile, result, log = ll.llm_draft(proved, name, draft_provider, draft_model,
                                            get_provider_api_key(db, draft_provider), out=out)
        record.update(draft_log=[{k: v for k, v in e.items() if k != 'examples'} for e in log],
                      draft_cost_usd=round(sum((e.get('usage') or {}).get('cost_usd', 0) for e in log), 4),
                      draft_model=draft_model)
        notes = []
    else:
        profile, result, notes = ll.draft(proved, proved, phrases, name)
    record.update(profile=profile, draft_notes=notes, test=dict(exact=result and result['exact'],
                                                               total=result and result['total'],
                                                               examples=result and result['examples']))
    if not profile or result['exact'] < result['total']:
        misses = [o for o in (result or {}).get('examples', []) if not o[-1].startswith('exact')]
        reason = 'The draft re-reads %s of %s proved statements exactly from the text (%s).' % (
            result and result['exact'] or 0, result and result['total'] or 0,
            '; '.join('%s %s: %s' % (m[0][:8], m[2], m[-1]) for m in misses[:4]))
        out('%s: %s' % (mark, reason))
        return ll.set_layout(mark, state='draft_failed', reason=reason, seconds=round(time.monotonic() - started, 1),
                             **record)
    if not gate:
        return ll.set_layout(mark, state='learning', reason='draft re-reads every example; gates not run', **record)
    gates = run_gates(profile, directory, truth, inventory, out=out)
    record['gates'] = dict(corpus=dict((k, gates['corpus'].get(k)) for k in ('files', 'unchanged', 'lost', 'changed',
                                                                          'gained', 'doubled', 'served_changed',
                                                                          'reason')),
                           rematched=[{k: e[k] for k in ('file', 'before', 'after', 'proved_before', 'proved_after')}
                                      for e in gates['corpus']['rematched']],
                           truth=dict((k, gates['truth'].get(k)) for k in ('wrong', 'lost', 'double', 'reason')),
                           truth_judged=len(gates['truth']['judged']))
    record['other_files'] = [e for e in record['gates']['rematched'] if e['file'] not in {f['file_id'] for f in proved}]
    state = 'passed' if gates['passed'] else 'gates_failed'
    reason = 'Both gates pass; awaiting the independent review.' if gates['passed'] else (
        'Gates failed: corpus lost %s changed %s doubled %s served-changed %s%s; truth wrong %s lost %s double %s%s.' % (
            len(gates['corpus']['lost']), len(gates['corpus']['changed']), len(gates['corpus']['doubled']),
            len(gates['corpus']['served_changed']),
            (' (%s)' % gates['corpus']['reason']) if gates['corpus'].get('reason') else '',
            len(gates['truth']['wrong']), len(gates['truth']['lost']), len(gates['truth']['double']),
            (' (%s)' % gates['truth']['reason']) if gates['truth'].get('reason') else ''))
    out('%s: %s' % (mark, reason))
    return ll.set_layout(mark, state=state, reason=reason, seconds=round(time.monotonic() - started, 1), **record)


def phrase_index(directory):
    """{file id: phrases} of every corpus file (layout_learning.cell_phrases), cached beside the corpus."""
    import pickle
    from services.financial import layout_learning as ll
    path = Path(directory, 'phrases.json')
    index = json.loads(path.read_text()) if path.exists() else {}
    changed = False
    for file_id, case_id, sources in corpus(directory):
        if file_id not in index:
            index[file_id] = sorted(ll.cell_phrases(ll.text_lines(sources)))
            changed = True
    if changed:
        path.write_text(json.dumps(index))
    return index


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    ex = sub.add_parser('examples')
    ex.add_argument('files', nargs='+')
    ex.add_argument('--budget', type=float, default=None)
    du = sub.add_parser('dump')
    du.add_argument('directory')
    du.add_argument('--shard', nargs=2, type=int, default=(0, 1))
    ga = sub.add_parser('gates')
    ga.add_argument('profile')
    ga.add_argument('--corpus', required=True)
    ga.add_argument('--truth', default='/mnt/owl-data/fin-real/truth')
    ga.add_argument('--inventory', default='/mnt/owl-data/fin-real/inventory.json')
    ga.add_argument('--off', nargs='*', default=[], help='written profiles to leave out (a backtest)')
    ga.add_argument('--json')
    le = sub.add_parser('learn')
    le.add_argument('--fingerprint', nargs='*')
    le.add_argument('--corpus', required=True)
    le.add_argument('--provider', help='page-image provider for a measurement (default: the workload setting)')
    le.add_argument('--model')
    le.add_argument('--drafter', choices=('derived', 'llm'), default='derived')
    le.add_argument('--draft-provider')
    le.add_argument('--draft-model')
    le.add_argument('--no-gates', action='store_true')
    le.add_argument('--truth', default='/mnt/owl-data/fin-real/truth')
    le.add_argument('--inventory', default='/mnt/owl-data/fin-real/inventory.json')
    args = parser.parse_args()
    if args.command == 'gates':
        result = run_gates(json.loads(Path(args.profile).read_text()), args.corpus, args.truth, args.inventory,
                           args.off)
        if args.json:
            Path(args.json).write_text(json.dumps(result, indent=1, default=str))
        print('Full results', 'PASS' if result['passed'] else 'FAIL')
        sys.exit(0 if result['passed'] else 1)
    from services.financial import layout_learning as ll
    db = _session()
    try:
        if args.command == 'examples':
            found, spent = examples(db, args.files, args.budget or ll.LAYOUT_BUDGET_USD)
            print('examples proved %s, cost %.4f USD' % (len(found), spent))
        elif args.command == 'learn':
            for mark, entries in register_layouts(args.fingerprint).items():
                record = learn_layout(db, mark, entries, args.corpus, provider=args.provider, model=args.model,
                                      drafter=args.drafter, draft_provider=args.draft_provider,
                                      draft_model=args.draft_model, truth=args.truth, inventory=args.inventory,
                                      gate=not args.no_gates)
                print('LAYOUT %s %s %s examples %s cost %s' % (mark, record['state'], record.get('reason'),
                                                             record.get('examples_proved'), record.get('cost_usd')),
                      flush=True)
            print('Full results learned')
        elif args.command == 'dump':
            dump(db, args.directory, *args.shard)
            print('Full results dumped')
    finally:
        db.rollback()


if __name__ == '__main__':
    main()
