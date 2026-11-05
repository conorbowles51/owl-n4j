"""Whole-case analyses: run once in the background, stored, and read a page at a time.

The workbench limits (500 transfer rows, 1,000 timeline rows, 200 patterns) bound the size of one synchronous answer,
not the analysis: Erica's 9,804 payments compare in 1.9 s of CPU and answer with 30.8 MB of JSON. Raising a limit is
what made pages hang, so a scope above a limit runs here instead:

* One short-lived child process per run (as view_warmup does), at background priority, one at a time (PDF reports in their own line) on this host.
  Its memory goes back to the system when it exits. It reads inside one read-only REPEATABLE READ snapshot.
* The result is written to files under the view memo directory (they survive a restart) as one JSON line per item,
  with an index of byte offsets, so a page costs a seek and is independent of the size of the result. Nothing is
  dropped: every item of the analysis is on disk, and every total shown is the count of the stored items.
* A run is identified by case, kind, parameters and code version; the same inputs and versions read the same stored
  answer, and its ``result_sha256`` is a digest of every stored line.
* A stored run is used only while the rows it read are unchanged (view_cache.fingerprint over the tables it read);
  otherwise it is run again. Nothing is invalidated by hand.
* A run that stops says so. The child records a heartbeat; when the server restarts, or the child dies, the run
  reports ``stopped`` with the reason and nothing partial is ever readable (the result is published last).
"""
import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from array import array
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from services.financial.ledger_summary import LedgerSummaryError

logger = logging.getLogger(__name__)

KINDS = ('transfers', 'timeline', 'patterns', 'trace', 'pdf')
PAGE_LIMIT = 200
HEARTBEAT_SECONDS = 5
STALE_HEARTBEAT_SECONDS = 180  # for a run whose child never recorded itself
# A child at background priority on a busy box can go minutes without a beat while its one long step holds the
# interpreter (seen at 3+ minutes in a PDF render at load 40-70), so a living child is only called hung well past that.
HUNG_HEARTBEAT_SECONDS = 1800
MAX_WAITING = 6
KEEP_SECONDS = 14 * 24 * 3600
KEEP_BYTES = 4 * 1024 ** 3
LOCK_NAME = 'host.lock'
# A PDF report takes hours on a large case; it waits only for another report, not a transfer comparison for it.
PDF_LOCK_NAME = 'pdf.lock'
STATE = 'state.json'
RESULT = 'result'
_ID = re.compile(r'^[a-f0-9]{32}$')
_SECTION = re.compile(r'^[a-z_]+(@[A-Za-z0-9_:-]{1,64})?$')


class WholeCaseRunError(LedgerSummaryError):
    """A refusal stated to the user; nothing partial is returned."""


def root():
    from services.financial import view_cache
    directory = view_cache._memo_dir()
    if directory is None:
        raise WholeCaseRunError('Whole-case runs need the saved-view folder, which is turned off on this server.')
    return directory / 'whole-case'


def run_id(kind, case_id, params):
    from services.financial.version import code_version
    identity = json.dumps([kind, str(case_id), params, code_version()], sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(identity.encode()).hexdigest()[:32]


def _write_state(directory, state):
    """Atomic: a reader sees the old state or the new one."""
    handle, name = tempfile.mkstemp(dir=directory, prefix='.state-')
    with os.fdopen(handle, 'w') as out:
        json.dump(state, out, sort_keys=True, separators=(',', ':'))
    os.replace(name, directory / STATE)


def _read_state(directory):
    try:
        return json.loads((directory / STATE).read_text())
    except (OSError, ValueError):
        return None


def _now():
    return datetime.now(timezone.utc).isoformat()


def _alive(pid, identifier):
    """This run's own child, not a later process that was given the same number."""
    try:
        with open('/proc/%d/cmdline' % int(pid), 'rb') as handle:
            return identifier.encode() in handle.read()
    except (OSError, TypeError, ValueError):
        return False


def view(state):
    """The state as a reader may see it: a run whose child is gone says it stopped, and why."""
    if state is None:
        return None
    if state['status'] in ('queued', 'running'):
        beat = state.get('heartbeat') or 0
        # No pid yet: the moment between recording the run and starting its child, under the start lock.
        pid = state.get('pid')
        silent = time.time() - beat
        if silent > STALE_HEARTBEAT_SECONDS if pid is None else (not _alive(pid, state['id']) or silent > HUNG_HEARTBEAT_SECONDS):
            state = {**state, 'status': 'stopped',
                     'error': 'This run stopped before it finished, most likely because the server restarted. '
                              'Nothing partial was kept. Run it again.'}
    return {key: value for key, value in state.items() if key not in ('pid', 'tables', 'fingerprint', 'heartbeat')}


def _current(engine, state, case_id):
    """Whether the rows this stored run read are unchanged; False when that cannot be shown."""
    from services.financial import view_cache
    if not state.get('tables') or state.get('fingerprint') is None:
        return False
    with engine.connect() as connection:
        connection = connection.execution_options(isolation_level='REPEATABLE READ')
        with connection.begin():
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            view_cache._load_tables(connection)
            now = view_cache.fingerprint(connection, tuple(state['tables']), case_id)
    return now is not None and json.loads(json.dumps(now)) == state['fingerprint']


def start_run(engine, *, kind, case_id, params):
    """The run for these inputs: its stored answer if still current, one already under way, or a new one."""
    import fcntl
    if kind not in KINDS:
        raise WholeCaseRunError('Unknown whole-case analysis.')
    base = root()
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    identifier = run_id(kind, case_id, params)
    directory = base / identifier
    with open(base / 'start.lock', 'a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        state = _read_state(directory)
        if state is not None:
            seen = view(state)
            if seen['status'] in ('queued', 'running'):
                return seen
            if seen['status'] == 'completed' and _current(engine, state, case_id):
                return seen
            shutil.rmtree(directory, ignore_errors=True)
        waiting = 0
        for other in base.iterdir():
            other_state = _read_state(other) if other.is_dir() else None
            if other_state and view(other_state)['status'] in ('queued', 'running'):
                waiting += 1
        if waiting >= MAX_WAITING:
            raise WholeCaseRunError('%d whole-case runs are already waiting on this server. Nothing was started; '
                                    'try again when one has finished.' % waiting)
        directory.mkdir(mode=0o700)
        state = dict(id=identifier, kind=kind, case_id=str(case_id), params=params, status='queued',
                     created_at=_now(), heartbeat=time.time(), phase='Starting the run',
                     step=0, steps=0, done=0, total=0)
        _write_state(directory, state)
        backend = Path(__file__).resolve().parents[2]
        child = subprocess.Popen([sys.executable, '-m', 'services.financial.whole_case_runs', '--run', identifier,
                                  '--parent', str(os.getpid())], cwd=str(backend), stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        # A short-lived thread collects the exit, so a finished child leaves no zombie behind.
        threading.Thread(target=child.wait, name='whole-case-wait', daemon=True).start()
        state['pid'] = child.pid
        current = _read_state(directory)
        if current is not None and current.get('pid') is None:  # the child may already have recorded itself
            current['pid'] = child.pid
            _write_state(directory, current)
        return view(_read_state(directory) or state)


def read_run(case_id, identifier):
    state = _load(case_id, identifier)
    return view(state)


def _load(case_id, identifier):
    """A run of this case. Another case's id reads as absent: access was checked for ``case_id`` only."""
    if not _ID.match(identifier or ''):
        raise WholeCaseRunError('Unknown whole-case run.')
    state = _read_state(root() / identifier)
    if state is None or state.get('case_id') != str(case_id):
        raise FileNotFoundError(identifier)
    return state


def _ready(case_id, identifier):
    state = _load(case_id, identifier)
    if state['status'] != 'completed':
        raise WholeCaseRunError('This run has not finished, so it has no pages yet.')
    return root() / identifier / RESULT


def _index(result, section):
    """(lines file, index file): ``name@subset`` is a subset of ``name``'s lines, in order."""
    if not _SECTION.match(section or ''):
        raise WholeCaseRunError('Unknown result section.')
    name = section.split('@')[0]
    return result / (name + '.jsonl'), result / (section + '.idx')


def read_page(case_id, identifier, section, *, offset=0, limit=50, search=None):
    """(total, offset, limit, encoded items) of a section. ``total`` is always the true count of stored items."""
    result = _ready(case_id, identifier)
    lines, index = _index(result, section)
    if not lines.exists() or not index.exists():
        raise FileNotFoundError(section)
    limit = max(1, min(int(limit), PAGE_LIMIT))
    offset = max(0, int(offset))
    if search:
        return _search_page(result, section, lines, index, offset, limit, search)
    width = array('Q').itemsize * 2
    total = index.stat().st_size // width
    spans = array('Q')
    with open(index, 'rb') as stream:
        stream.seek(offset * width)
        spans.frombytes(stream.read(limit * width))
    return total, offset, limit, _lines(lines, spans)


def _lines(path, spans):
    items = []
    with open(path, 'rb') as stream:
        for start, end in zip(spans[0::2], spans[1::2]):
            stream.seek(start)
            items.append(stream.read(end - start).rstrip(b'\n'))
    return items


def _search_page(result, section, lines, index, offset, limit, search):
    """Search over the words stored for each item (its values, not its field names); the count is every match."""
    words = result / (section.split('@')[0] + '.words')
    if not words.exists():
        raise WholeCaseRunError('This list cannot be searched.')
    spans = array('Q')
    with open(index, 'rb') as stream:
        spans.frombytes(stream.read())
    wanted = search.strip().lower().encode()
    if section.split('@')[0] != section:
        keep = {start for start in spans[0::2]}
    else:
        keep = None
    full = array('Q')
    with open(_index(result, section.split('@')[0])[1], 'rb') as stream:
        full.frombytes(stream.read())
    found = array('Q')
    with open(words, 'rb') as stream:
        for number, text in enumerate(stream):
            if wanted in text:
                start, end = full[number * 2], full[number * 2 + 1]
                if keep is None or start in keep:
                    found.extend((start, end))
    total = len(found) // 2
    return total, offset, limit, _lines(lines, found[offset * 2:(offset + limit) * 2])


def read_file(case_id, identifier, name):
    """A finished run's stored file, for a download of the whole list."""
    result = _ready(case_id, identifier)
    if not re.fullmatch(r'[a-z_]+\.jsonl|[a-z0-9_-]+\.(json|zip)', name or ''):
        raise FileNotFoundError(name)
    path = result / name
    if not path.is_file():
        raise FileNotFoundError(name)
    return path


def transfer_scenario(engine, *, case_id, identifier, request):
    """The conditional totals for pairs chosen from a stored comparison: the stored rows and candidates are the
    comparison, so nothing is computed again; refused when any row it read has changed. The report carries the rows
    of the chosen pairs and the fingerprint of the whole scope (a whole case does not fit a 16 MiB report)."""
    from services.financial.ledger_transfers import LedgerTransferScenario, scenario_figures, SCENARIO_LIMITATION
    from services.financial.ledger_snapshot import MAX_EXPORT_BYTES
    request = LedgerTransferScenario.model_validate(request)
    if not request.basis.strip():
        raise LedgerSummaryError('Record a reason for the selected pairings.')
    state = _load(case_id, identifier)
    result = _ready(case_id, identifier)
    summary = state.get('summary') or {}
    if state['kind'] != 'transfers':
        raise WholeCaseRunError('Only a transfer comparison can be paired.')
    if not _current(engine, state, case_id) or request.expected_snapshot_sha256 != summary['snapshot_sha256']:
        raise LedgerSummaryError('Ledger readings or decisions changed. Reload transfer candidates before pairing.')
    if (request.population != summary['population'] or request.tolerance_days != summary['tolerance_days']
            or (request.start_date.isoformat() if request.start_date else None) != summary['start_date']
            or (request.end_date.isoformat() if request.end_date else None) != summary['end_date']):
        raise LedgerSummaryError('Transfer scenario date scope differs from its captured ledger.')
    indexed = {}
    with open(result / 'candidates.jsonl', 'rb') as stream:
        for line in stream:
            pair = json.loads(line)
            indexed[(pair['debit_id'], pair['credit_id'])] = pair
    used, selected = set(), []
    for choice in request.pairs:
        key = (str(choice.debit_id), str(choice.credit_id))
        if key not in indexed or any(value in used for value in key):
            raise LedgerSummaryError('Choose proposed pairs without using a reading more than once.')
        used.update(key)
        selected.append(indexed[key])
    rows = []
    with open(result / 'rows.jsonl', 'rb') as stream:
        for line in stream:
            row = json.loads(line)
            if row['key'] in used:
                rows.append(row)
    figures = scenario_figures(selected, summary['currencies'])
    document = dict(schema='loupe.financial.transfer_scenario/1', case_id=summary['case_id'], applied=False, pairings_verified=False,
                    inputs=request.model_dump(mode='json'), selected_pairs=[{key: value for key, value in pair.items() if key not in ('debit', 'credit')}
                                                                            for pair in selected], selected_rows=rows, figures=figures,
                    ledger_scope=dict(snapshot_sha256=summary['snapshot_sha256'], digest_covers=summary['digest_covers'],
                                      run_id=state['id'], result_sha256=state['result_sha256'], code_version=state['code_version']),
                    limitation=SCENARIO_LIMITATION + ' This whole-case report names the fingerprint of the full ledger scope and carries only '
                                                     'the chosen rows; the full scope is in the stored run and a ledger export.')
    content = json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    encoded = content.encode('utf-8')
    if len(encoded) > MAX_EXPORT_BYTES:
        raise LedgerSummaryError('Transfer report exceeds 16 MiB; no partial report was returned.')
    return dict(case_id=summary['case_id'], applied=False, figures=figures, scenario_json=content,
                scenario_sha256=hashlib.sha256(encoded).hexdigest(), scenario_byte_count=len(encoded))


# --- the child -----------------------------------------------------------------------------------------------------

class _Run:
    def __init__(self, directory, state):
        self.directory, self.state = directory, state
        self.lock = threading.Lock()
        self.after_publish = None

    def write(self, **changes):
        with self.lock:
            self.state.update(changes, heartbeat=time.time())
            _write_state(self.directory, self.state)

    def phase(self, step, steps, label, *, done=0, total=0):
        self.write(step=step, steps=steps, phase=label, done=done, total=total)

    def done(self, done):
        # Progress is frequent; the state file is written at most twice a second.
        if time.time() - self.state.get('heartbeat', 0) >= 0.5:
            self.write(done=done)


class _Writer:
    """One section: its JSON lines, the offsets of each line, subsets by key, and optional search words."""

    def __init__(self, directory, name):
        self.directory, self.name = directory, name
        self.lines = open(directory / (name + '.jsonl'), 'wb')
        self.offsets = array('Q')
        self.subsets = {}
        self.words = None
        self.position = 0

    def add(self, item, *, subset=None, words=None):
        encoded = json.dumps(item, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode() + b'\n'
        self.lines.write(encoded)
        span = (self.position, self.position + len(encoded))
        self.position += len(encoded)
        self.offsets.extend(span)
        if subset is not None:
            for key in ([subset] if isinstance(subset, str) else subset):
                self.subsets.setdefault(key, array('Q')).extend(span)
        if words is not None:
            if self.words is None:
                self.words = open(self.directory / (self.name + '.words'), 'wb')
            self.words.write(' '.join(str(w) for w in words if w is not None).lower().replace('\n', ' ').encode() + b'\n')
        return encoded

    def close(self):
        self.lines.close()
        if self.words is not None:
            self.words.close()
        with open(self.directory / (self.name + '.idx'), 'wb') as stream:
            self.offsets.tofile(stream)
        for key, spans in self.subsets.items():
            with open(self.directory / ('%s@%s.idx' % (self.name, key)), 'wb') as stream:
                spans.tofile(stream)
        return len(self.offsets) // 2


def _write_sections(directory, sections, run, step, steps):
    """Write {name: [(item, subset, words)]}; returns (counts, sha256 over every line in section order)."""
    total = sum(len(items) for items in sections.values())
    run.phase(step, steps, 'Saving the results', done=0, total=total)
    digest, counts, done = hashlib.sha256(), {}, 0
    for name in sorted(sections):
        writer = _Writer(directory, name)
        digest.update(name.encode() + b'\n')
        for item, subset, words in sections[name]:
            digest.update(writer.add(item, subset=subset, words=words))
            done += 1
            if done % 500 == 0:
                run.done(done)
        counts[name] = writer.close()
        for key, spans in writer.subsets.items():
            counts['%s@%s' % (name, key)] = len(spans) // 2
    run.done(done)
    return counts, digest.hexdigest()


def _capture(connection, case_id, params, kind, identifier):
    from services.financial.ledger_snapshot import capture_ledger_export, capture_ledger_scope
    def day(name):
        from datetime import date
        return date.fromisoformat(params[name]) if params.get(name) else None
    def ids(name):
        return [UUID(value) for value in params[name]] if params.get(name) else None
    scope = dict(case_id=case_id, account_id=UUID(params['account_id']) if params.get('account_id') else None, account_ids=ids('account_ids'),
                 account_holders=params.get('account_holders') or None, start_date=day('start_date'), end_date=day('end_date'))
    if kind == 'pdf':
        return capture_ledger_export(connection, generated_by=params.get('generated_by'), privilege_marking=params.get('privilege_marking', 'unmarked'),
                                     size_limit=False, generated_at=_export_time(identifier), **scope)
    return capture_ledger_scope(connection, **scope)


def _pair_side(row):
    return dict(key=row['key'], account_id=row['account_id'], account_label=row.get('account_label'),
                ordering_date=row['ordering_date'], description=row.get('description'))


def compute_transfers(capture, params, run):
    from services.financial.ledger_transfers import ledger_transfer_candidates
    result = ledger_transfer_candidates(capture, population=params['population'], tolerance_days=params['tolerance_days'],
                                        grade=True, whole_case=True)
    by_id = {row['key']: row for row in result['rows']}
    graded = result['graded']
    def side(item):
        return {**item, 'debit': _pair_side(by_id[item['debit_id']]), 'credit': _pair_side(by_id[item['credit_id']])}
    def row_words(row):
        return (row['ordering_date'], row.get('account_label'), row['direction'], row.get('description'), row.get('from_name'), row.get('to_name'),
                row.get('txn_number'), row['currency'], row['amount_minor'])
    def pair_words(pair):
        return row_words(by_id[pair['debit_id']]) + row_words(by_id[pair['credit_id']])
    sections = dict(
        rows=[(row, row['direction'], row_words(row)) for row in result['rows']],
        candidates=[(side(pair), None, pair_words(pair)) for pair in result['candidates']],
        graded=[(side(pair), pair['level'], None) for pair in graded['pairs']],
        reference_evidence=[(item, None, None) for item in result['reference_evidence']])
    summary = {key: result[key] for key in ('case_id', 'start_date', 'end_date', 'population', 'tolerance_days', 'snapshot_sha256',
                                            'digest_covers', 'currencies', 'excluded_rows', 'limitation', 'applied')}
    summary.update(by_level=graded['by_level'], left_out=graded['left_out'], left_out_words=graded['left_out_words'], rule=graded['rule'],
                   date_unavailable_count=len(result['date_unavailable_ids']), unscoped_reference_count=len(result['unscoped_reference_ids']))
    return summary, sections


def compute_timeline(capture, params, run):
    from services.financial.ledger_timeline import ledger_timeline
    result = ledger_timeline(capture, population=params['population'], whole_case=True)
    months, rows = {}, []
    for row in result['rows']:
        month = row['chronology_date'][:7]
        entry = months.setdefault(month, dict(month=month, payments=0, debits=0, credits=0, totals={}))
        entry['payments'] += 1
        entry['credits' if row['direction'] == 'credit' else 'debits'] += 1
        money = entry['totals'].setdefault(row['currency'], dict(credits_minor=0, debits_minor=0))
        money['credits_minor' if row['direction'] == 'credit' else 'debits_minor'] += int(row['amount_minor'])
        rows.append((row, month, (row['chronology_date'], row.get('account_label'), row['direction'], row.get('description'),
                                  row.get('from_name'), row.get('to_name'), row.get('txn_number'), row['currency'], row['amount_minor'])))
    for entry in months.values():
        entry['totals'] = {currency: {key: str(value) for key, value in money.items()} for currency, money in sorted(entry['totals'].items())}
    summary = {key: result[key] for key in ('case_id', 'account_id', 'start_date', 'end_date', 'population', 'snapshot_sha256',
                                            'digest_covers', 'excluded_rows', 'limitation')}
    summary['months'] = [months[key] for key in sorted(months)]
    return summary, dict(rows=rows)


def compute_patterns(capture, params, run):
    from services.financial.pattern_review import screen_ledger_patterns
    threshold = params.get('threshold_minor')
    result = screen_ledger_patterns(capture, population=params['population'], window_days=params['window_days'],
                                    threshold_minor=int(threshold) if threshold else None,
                                    threshold_currency=params.get('threshold_currency'),
                                    cross_account=params.get('cross_account', False), whole_case=True)
    sources, hypotheses, kinds = [], [], {}
    for hypothesis in result['hypotheses']:
        members = hypothesis['sources']
        kinds[hypothesis['kind']] = kinds.get(hypothesis['kind'], 0) + 1
        item = {**hypothesis, 'sources': members[:SOURCES_SHOWN], 'sources_total': len(members), 'sources_start': len(sources)}
        if len(members) > SOURCES_SHOWN:  # the rest open a page at a time; a smaller group is complete on its own line
            sources.extend((member, None, None) for member in members)
        hypotheses.append((item, hypothesis['kind'], (hypothesis['kind'], hypothesis['account_label'], hypothesis.get('counterparty_label'),
                                                     hypothesis['currency'], hypothesis['amount_minor'], hypothesis['explanation'])))
    summary = {key: result[key] for key in result if key not in ('hypotheses', 'date_unavailable_ids')}
    summary.update(by_kind=kinds, date_unavailable_count=len(result['date_unavailable_ids']))
    return summary, dict(hypotheses=hypotheses, sources=sources,
                         date_unavailable=[(dict(key=key), None, None) for key in result['date_unavailable_ids']])


def compute_trace(capture, params, run):
    from services.financial.trace_walk import trace_walk
    summary, report = trace_walk(capture, params)
    return summary, dict(files={'trace-report.json': report})


def _resume_dir(identifier):
    """What a stopped report keeps for its next run; removed when the report is finished."""
    directory = root() / 'resume' / identifier
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def _export_time(identifier):
    """The report's generation time, the same across a restart, so a part already written stays the same part."""
    path = _resume_dir(identifier) / 'generated_at'
    if not path.exists():
        path.write_text(_now())
    return datetime.fromisoformat(path.read_text())


def compute_pdf(capture, params, run):
    """Numbered PDF parts covering every captured reading, in one archive, with a manifest of each part's digest."""
    import io
    import zipfile
    from services.financial.ledger_pdf import numbered_report_parts, render_ledger_pdf
    from services.financial.ledger_snapshot import LedgerSnapshot, render_ledger_report
    parts = list(numbered_report_parts(capture.snapshot))
    listed, members = [], []
    run.phase(2, 3, 'Writing the PDF parts', done=0, total=len(parts))
    resume = _resume_dir(params['run_id'])
    for number, of, document, words in parts:
        content = json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
        part = LedgerSnapshot(content, hashlib.sha256(content.encode()).hexdigest(), len(content.encode()))
        # A part already written from these same bytes is kept across a restart: a release does not start the report over.
        finished = resume / (part.sha256 + '.pdf')
        if finished.exists():
            pdf = finished.read_bytes()
        else:
            pdf = render_ledger_pdf(part, render_ledger_report(part), part_words=words)
            waiting = resume / (part.sha256 + '.tmp')
            waiting.write_bytes(pdf)
            os.replace(waiting, finished)
        name = 'ledger-report-part-%03d-of-%03d.pdf' % (number, of)
        keys = sorted(reading['row']['key'] for reading in document['ledger']['readings'])
        listed.append(dict(part=number, of=of, filename=name, readings=len(keys), sha256=hashlib.sha256(pdf).hexdigest(), byte_count=len(pdf),
                           first_key=keys[0] if keys else None, last_key=keys[-1] if keys else None, words=words))
        members.append((name, pdf))
        run.phase(2, 3, 'Writing the PDF parts', done=number, total=of)
    readings = json.loads(capture.snapshot.content)['ledger']['readings']
    manifest = dict(schema='loupe.financial.ledger_pdf_parts/1', snapshot_sha256=capture.snapshot.sha256, ledger_scope_sha256=capture.ledger_scope_sha256,
                    digest_covers='The full export document; the snapshot itself stays available through a ledger export.',
                    readings=len(readings), parts=listed, covers_every_reading=sum(item['readings'] for item in listed) == len(readings))
    if not manifest['covers_every_reading']:
        raise WholeCaseRunError('The numbered parts did not cover every captured payment; no report was produced.')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(zipfile.ZipInfo('parts-manifest.json', date_time=(1980, 1, 1, 0, 0, 0)), json.dumps(manifest, sort_keys=True, indent=1))
        for name, pdf in members:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, pdf)
    data = stream.getvalue()
    run.after_publish = lambda: shutil.rmtree(resume, ignore_errors=True)
    summary = dict(case_id=str(params['case_id']), snapshot_sha256=capture.snapshot.sha256, readings=len(readings), parts=len(listed),
                   part_limit=max(item['readings'] for item in listed), archive_sha256=hashlib.sha256(data).hexdigest(), archive_bytes=len(data),
                   filename='ledger-report-parts.zip', listed=[{key: item[key] for key in ('part', 'of', 'filename', 'readings', 'byte_count', 'words')} for item in listed])
    return summary, dict(files={'ledger-report-parts.zip': data})


SOURCES_SHOWN = 50
COMPUTE = dict(transfers=compute_transfers, timeline=compute_timeline, patterns=compute_patterns, trace=compute_trace, pdf=compute_pdf)
COMPUTE_LABEL = dict(transfers='Comparing every payment by amount and date', timeline='Putting the payments in date order',
                     patterns='Screening the payments for patterns', trace='Following the selected transfers from the start point',
                     pdf='Writing the PDF parts')


def _execute(run):
    from sqlalchemy.orm import Session  # noqa: F401 - keeps the import failure inside the run's own error handling
    from postgres.session import _get_engine
    from services.financial import view_cache
    from services.financial.version import code_version
    state = run.state
    case_id, params, kind = UUID(state['case_id']), state['params'], state['kind']
    steps = 3
    started = time.time()
    run.write(status='running', started_at=_now())
    run.phase(1, steps, 'Reading the payments and their decisions')
    engine = _get_engine()
    with engine.connect() as owner:
        owner = owner.execution_options(isolation_level='REPEATABLE READ')
        with owner.begin():
            owner.exec_driver_sql('SET TRANSACTION READ ONLY')
            snapshot = owner.exec_driver_sql('SELECT pg_export_snapshot()').scalar()
            view_cache._load_tables(owner)
            # The same recording a cached view uses: every table read is named, so a change to any of them is seen.
            recording = view_cache._Recording(owner=view_cache._dbapi(owner), snapshot=snapshot, connection=owner, view='whole-case-' + kind)
            token = view_cache._recording.set(recording)
            try:
                capture = _capture(owner, case_id, params, kind, state['id'])
                run.phase(2, steps, COMPUTE_LABEL[kind])
                summary, sections = COMPUTE[kind](capture, {**params, 'case_id': state['case_id'], 'run_id': state['id']}, run)
            finally:
                recording.paused = True
                view_cache._recording.reset(token)
            tables = sorted(recording.tables)
            fingerprint = view_cache.fingerprint(owner, tuple(tables), case_id)
    work = tempfile.mkdtemp(dir=run.directory, prefix='.work-')
    files = sections.pop('files', {})
    counts, digest = _write_sections(Path(work), sections, run, 3, steps)
    for name, content in files.items():
        (Path(work) / name).write_bytes(content)
    with open(Path(work) / 'summary.json', 'w') as out:
        json.dump(summary, out, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    # Published last, in one rename: no reader ever sees part of a result.
    os.replace(work, run.directory / RESULT)
    run.write(status='completed', completed_at=_now(), seconds=round(time.time() - started, 1), counts=counts, summary=summary,
              result_sha256=digest, code_version=code_version(), tables=tables,
              fingerprint=json.loads(json.dumps(fingerprint)) if fingerprint is not None else None,
              phase='Finished', step=steps, steps=steps, done=sum(len(v) for v in sections.values()),
              total=sum(len(v) for v in sections.values()))
    if run.after_publish:
        run.after_publish()


def _prune(base, keep):
    """Oldest finished runs go first, past 14 days or 4 GiB; they can always be run again."""
    entries = []
    for path in (base / 'resume').iterdir() if (base / 'resume').is_dir() else ():
        if time.time() - path.stat().st_mtime > KEEP_SECONDS:
            shutil.rmtree(path, ignore_errors=True)
    for path in base.iterdir():
        state = _read_state(path) if path.is_dir() else None
        if path == keep or state is None or view(state)['status'] in ('queued', 'running'):
            continue
        size = sum(item.stat().st_size for item in path.rglob('*') if item.is_file())
        entries.append(((path / STATE).stat().st_mtime, size, path))
    entries.sort(key=lambda entry: entry[0])
    total = sum(entry[1] for entry in entries)
    for modified, size, path in entries:
        if time.time() - modified > KEEP_SECONDS or total > KEEP_BYTES:
            shutil.rmtree(path, ignore_errors=True)
            total -= size


def main(identifier, parent):
    import fcntl
    from services.financial.view_warmup import _lower_priority
    _lower_priority()
    base = root()
    directory = base / identifier
    state = _read_state(directory)
    if state is None:
        return 1
    state['pid'] = os.getpid()
    run = _Run(directory, state)
    run.write()
    finished = threading.Event()

    def stop(reason):
        if run.state.get('status') != 'completed':
            run.write(status='stopped', error=reason)
        os._exit(0)

    def beat():
        while not finished.wait(HEARTBEAT_SECONDS):
            if os.getppid() != parent:
                stop('The server restarted while this ran. Nothing partial was kept. Run it again.')
            run.write()
    threading.Thread(target=beat, name='whole-case-heartbeat', daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: stop('The server restarted while this ran. Nothing partial was kept. Run it again.'))
    try:
        with open(base / (PDF_LOCK_NAME if state['kind'] == 'pdf' else LOCK_NAME), 'a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                run.write(phase='Waiting for an earlier run to finish')
                fcntl.flock(lock, fcntl.LOCK_EX)
            _execute(run)
        _prune(base, directory)
    except LedgerSummaryError as error:
        run.write(status='failed', error=str(error))
    except Exception:  # noqa: BLE001 - the run says it failed; the journal has the detail
        logger.exception('Whole-case run %s failed', identifier)
        run.write(status='failed', error='This run could not be finished. Nothing partial was kept. Run it again.')
    finished.set()
    return 0


if __name__ == '__main__':
    arguments = argparse.ArgumentParser()
    arguments.add_argument('--run', required=True)
    arguments.add_argument('--parent', required=True, type=int)
    options = arguments.parse_args()
    sys.exit(main(options.run, options.parent))
