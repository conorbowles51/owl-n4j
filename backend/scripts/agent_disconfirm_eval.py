"""Evaluation set for the disconfirm sweep (agent-disconfirm E): theories with known contradicting items, on the live
model, through the live API, signed in.

Each theory is synthetic and sits in the Phone training check case, whose records are invented. ``planted`` names the
records that contradict it: ledger rows by id prefix, phone messages by exact text, statement pages by file name.
Controls state what the records do show: anything proposed against a control is a candidate false finding.

Recall: planted items cited by a proposal, of those planted; a theory counts as caught when at least one is. A ledger
row counts when the proposal cites the row, or cites the statement file the row was read from and states the row's
amount. A proposal citing no planted item is listed for a person to judge, with its text. This script judges nothing
beyond that match.

    python scripts/agent_disconfirm_eval.py --out DIR [--only T1,T2] [--no-reads] [--parallel 3]

A release in the middle costs the reads that were out: a stopped plan is planned again and stopped reads are started
again, which sends only what was not read.

Login: LOUPE_LOGIN_FILE (key=value: email, password, url). Writes only in the check case.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CASE = 'd9945277-6c80-4a39-82c7-93a95d420384'
RELEASE_CAP = 3600
WATERMARK = re.compile(r'invented data|(statements?|data|records?) (is|are|as) synthetic|(labell?ed|marked|flagged) (as )?synthetic'
                       r'|synthetic[,/ ]+(not real|invented)', re.I)  # the check files' own printed notice
RUN = os.environ.get('DISCONFIRM_EVAL_RUN', '2')  # each evaluation has its own theories: a rerun would be all repeats
THEORIES = [
    dict(id='T1', title='Juniper never paid Ashdown',
         body='Emrys Juniper has never paid Dorian Ashdown any money from his account.',
         planted=dict(txn=['be3aa3fb', '61d0a15d', '634e92dd', 'bcc5aa4d'])),
    dict(id='T2', title='Northcott Storage only ever received money from Juniper',
         body='Northcott Storage Ltd is only a recipient: it received money from Emrys Juniper and never paid him.',
         planted=dict(txn=['1de6fccf', '2e95483b', 'bf293fc1'])),
    dict(id='T3', title='Harrowgate paid nothing before February 2024',
         body='Avery Harrowgate made no payment into the Juniper account before 1 February 2024.',
         planted=dict(txn=['6a19fbc8', '1a43ac18'])),
    dict(id='T4', title='Ellis Greywell never repaid Juniper',
         body='Ellis Greywell took money from Emrys Juniper and never sent any back.',
         planted=dict(txn=['0bb40876', '01b056ea'])),
    dict(id='T5', title='Dealings with Synthetic Grocers stopped in March 2024',
         body='The Juniper account had no dealings at all with Synthetic Grocers after 31 March 2024.',
         planted=dict(txn=['402b8a55', '676611f0', '9e619333', 'e4371c37'])),
    dict(id='T6', title='No deposit above 800 dollars',
         body='No single payment into the Juniper account was ever more than 800.00 USD.',
         planted=dict(txn=['01b056ea', '293339d6', '61fbb9f0', 'c2a09195'])),
    dict(id='T7', title='Juniper and Dorian had no phone contact',
         body='Emrys Juniper and Dorian Ashdown were never in touch by phone: no call or message between them on any '
              'phone in the case.', planted=dict(party='Dorian')),
    dict(id='T8', title='Nobody discussed paying in instalments',
         body='Nobody on these phones ever discussed splitting a payment into instalments or part payments.',
         planted=dict(text=['half now, half on Friday'])),
    dict(id='T9', title='Nothing was ever kept quiet',
         body='The messages are all open and ordinary. Nobody on these phones ever asked anyone to keep something '
              'secret or between themselves.', planted=dict(text=['keep this between us'])),
    dict(id='T10', title='No package was ever mentioned',
         body='These people never exchanged goods: no message on any phone mentions a package or a delivery.',
         planted=dict(text=['did you get the package', 'left it by the side door'])),
    dict(id='T11', title="Juniper's phone was never near Baltimore",
         body="The phones in this case were only ever in New York; none was ever recorded in Maryland or near "
              'Baltimore.', planted=dict(places=True)),
    dict(id='T12', title='The account belongs to Nell Merriweather',
         body='The Synthetic Community Bank account ending 0100 is held by Nell Merriweather, not by Emrys Juniper.',
         planted=dict(doc=['statement-'])),
    dict(id='C1', title='Juniper paid Wren Pennywhistle in November 2023', control=True,
         body='Emrys Juniper paid Wren Pennywhistle from his account in November 2023.', planted={}),
    dict(id='C2', title='Northcott Storage paid Juniper in November 2023', control=True,
         body='Northcott Storage Ltd paid money into the Juniper account in November 2023.', planted={}),
    dict(id='C3', title='The account is held at Synthetic Community Bank', control=True,
         body='Emrys Juniper holds an account at Synthetic Community Bank.', planted={}),
]


def psql(sql: str) -> list[list[str]]:
    db = subprocess.check_output(['docker', 'exec', 'owl-v2-pg', 'sh', '-c', 'echo $POSTGRES_DB'], text=True).strip()
    full = "SET default_transaction_read_only=on;\n\\pset format unaligned\n\\pset fieldsep '\\t'\n\\pset tuples_only on\n" + sql
    out = subprocess.run(['docker', 'exec', '-i', 'owl-v2-pg', 'psql', '-q', '-U', 'owl_us', '-d', db], input=full,
                         capture_output=True, text=True, check=True).stdout
    return [line.split('\t') for line in out.splitlines() if '\t' in line]


def planted_keys(theory) -> set[str]:
    """The citations that count, from the live rows, read-only."""
    p = theory['planted']
    keys = set()
    if p.get('txn'):
        wanted = ' OR '.join(f"id::text LIKE '{x}%'" for x in p['txn'])
        keys |= {f'txn://{r[0]}' for r in psql(f"SELECT id, 1 FROM financial_transactions WHERE case_id='{CASE}' AND ({wanted});")}
    for body in p.get('text') or []:
        keys |= {f'rec://{r[0]}' for r in psql(f"SELECT record_uid, 1 FROM pv_comm_event WHERE case_id='{CASE}' AND body='{body}';")}
    if p.get('party'):
        keys |= {f'rec://{r[0]}' for r in psql(
            f"SELECT DISTINCT e.record_uid, 1 FROM pv_comm_event e JOIN pv_comm_party c ON c.event_uid=e.event_uid JOIN pv_identity_name n "
            f"ON n.identity_id=(SELECT i.identity_id FROM pv_identity i WHERE i.identity_key=c.identity_key AND i.case_id='{CASE}' LIMIT 1) "
            f"WHERE e.case_id='{CASE}' AND n.name ILIKE '%{p['party']}%';")}
    if p.get('places'):
        keys |= {f'rec://{r[0]}' for r in psql(f"SELECT record_uid, 1 FROM pv_location_point WHERE case_id='{CASE}' "
                                               'AND lat BETWEEN 37.9 AND 39.8 AND lon BETWEEN -79.5 AND -75.0;')}  # Maryland
    for name in p.get('doc') or []:
        keys |= {f'doc://{r[0]}' for r in psql(f"SELECT id, 1 FROM evidence_files WHERE case_id='{CASE}' AND original_filename LIKE '{name}%';")}
    return keys


def statement_lines(theory) -> dict:
    """Planted ledger row -> (statement file, amount): what a proposal citing the page instead of the row must state."""
    if not theory['planted'].get('txn'):
        return {}
    wanted = ' OR '.join(f"id::text LIKE '{x}%'" for x in theory['planted']['txn'])
    rows = psql(f"SELECT t.id, d.evidence_file_id, t.amount_minor FROM financial_transactions t JOIN financial_source_documents d "
                f"ON d.id=t.source_document_id WHERE t.case_id='{CASE}' AND ({wanted.replace('id::text', 't.id::text')});")
    return {f'txn://{r[0]}': (f'doc://{r[1]}', f'{int(r[2]) / 100:.2f}') for r in rows}


class Api:
    def __init__(self, login_file):
        self.login_file = login_file
        self.base = self.login()['url'].strip().rstrip('/')
        self.token = None
        self.signing = threading.Lock()
        self.sign_in(None)

    def login(self):
        """Read at every sign-in: the shared login's password can change during a run."""
        return dict(line.split('=', 1) for line in Path(self.login_file).read_text().splitlines() if '=' in line)

    def sign_in(self, stale):
        """One sign-in however many theories hit the expired token at once; never leaves the others without one."""
        with self.signing:
            if self.token != stale:
                return
            cred = self.login()
            data = json.dumps(dict(username=cred['email'].strip(), password=cred['password'].strip())).encode()
            req = urllib.request.Request(self.base + '/api/auth/login', data=data, method='POST',
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=120) as resp:
                self.token = json.loads(resp.read())['access_token']

    def _call(self, method, path, body=None, retried=False, began=None):
        began = began or time.time()
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={'Content-Type': 'application/json'})
        token = self.token
        req.add_header('Authorization', f'Bearer {token}')
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read() or 'null')
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and not retried:
                self.sign_in(token)
                return self._call(method, path, body, True, began)
            if exc.code < 502:
                raise RuntimeError(f'{method} {path}: {exc.code} {exc.read()[:300]!r}') from exc
        except (urllib.error.URLError, OSError):
            pass
        if time.time() - began > RELEASE_CAP:  # a release, or the box under load: every minute until the cap
            raise RuntimeError(f'{method} {path}: no answer for {RELEASE_CAP} s')
        time.sleep(60)
        return self._call(method, path, body, retried, began)

    def get(self, path):
        return self._call('GET', path)

    def post(self, path, body=None):
        return self._call('POST', path, body if body is not None else {})


def wait(api, theory_id, want, cap=7200):
    """Until ``want``, picking a sweep up again when a release stopped it."""
    began = time.time()
    while time.time() - began < cap:
        state = api.get(f'/api/workspace/{CASE}/proposals/disconfirm?theory_id={theory_id}')
        sweep = state['sweep']
        if sweep and want(sweep):
            return sweep
        if sweep and sweep['job_status'] == 'failed' and 'restarted' in (sweep.get('error') or ''):
            print(time.strftime('%H:%M:%S'), theory_id, 'picked up after a restart:', sweep['stage'], flush=True)
            if sweep['stage'] == 'planning':
                api.post(f'/api/workspace/{CASE}/proposals/disconfirm', dict(theory_id=theory_id))
            else:
                api.post(f"/api/workspace/{CASE}/proposals/disconfirm/{sweep['id']}/start", {})
        time.sleep(10)
    raise TimeoutError(theory_id)


def run_one(api, theory, state, out, lock, reads=True):
    t = dict(state.get(theory['id']) or {})
    if not t.get('entry'):
        made = api.post(f'/api/workspace/{CASE}/entries', dict(entry_type='theory', title=f"[Disconfirm evaluation {RUN}] {theory['title']}",
                                                               body=theory['body'], lifecycle_state='proposed'))
        t['entry'] = made['id']
    with lock:
        state[theory['id']] = t
        out.write_text(json.dumps(state, indent=1))
    sweep = api.get(f"/api/workspace/{CASE}/proposals/disconfirm?theory_id={t['entry']}")['sweep']
    began = time.time()
    if sweep is None or (sweep['stage'] == 'planning' and sweep['job_status'] == 'failed'):
        sweep = api.post(f'/api/workspace/{CASE}/proposals/disconfirm', dict(theory_id=t['entry']))
    sweep = wait(api, t['entry'], lambda s: s['job_status'] not in ('queued', 'running') and not (
        s['job_status'] == 'failed' and 'restarted' in (s.get('error') or '')))
    t['plan_seconds'] = round(time.time() - began, 1)
    if sweep['stage'] == 'planning':
        t['error'] = sweep['error']
        return t
    if reads and sweep['stage'] == 'planned':
        began = time.time()
        api.post(f"/api/workspace/{CASE}/proposals/disconfirm/{sweep['id']}/start", {})
        sweep = wait(api, t['entry'], lambda s: s['stage'] == 'done' and s['job_status'] not in ('queued', 'running'))
        t['read_seconds'] = round(time.time() - began, 1)
    t['sweep'] = {k: sweep.get(k) for k in ('id', 'stage', 'expectations', 'cost', 'absences', 'refused', 'repeats', 'proposals',
                                            'fold', 'model', 'calls_stated', 'census')}
    t['reads'] = sweep['reads']
    t['outcome'] = sweep['outcome']
    return t


def score(api, theory, t):
    keys = planted_keys(theory)
    listed, offset = [], 0
    while True:
        page = api.get(f'/api/workspace/{CASE}/proposals?status=all&output_type=counter_argument&limit=100&offset={offset}')
        listed += page['items']
        offset += 100
        if len(page['items']) < 100:
            break
    mine = [p for p in listed if p['content'].get('theory_id') == t.get('entry')]
    lines = statement_lines(theory)
    cited, loose = set(), []
    for p in mine:
        cites = {c.split('#')[0] for c in p['content'].get('citations') or []}
        norm = {c if not c.startswith('doc://') else '/'.join(c.split('/')[:3]) for c in cites}
        hit = norm & keys
        hit |= {key for key, (doc, amount) in lines.items()
                if doc in norm and amount in (p['content'].get('body') or '').replace(',', '')}
        cited |= hit
        if not hit:
            loose.append(dict(title=p['content'].get('title'), body=p['content'].get('body'), strength=p['content'].get('strength'),
                              expectation=p['content'].get('expectation'), citations=sorted(cites)))
    for row in loose:
        row['watermark'] = bool(WATERMARK.search(row['body'] or ''))
    return dict(id=theory['id'], control=bool(theory.get('control')), planted=len(keys), planted_cited=len(cited),
                caught=bool(cited) if keys else None, proposals=len(mine), not_on_planted=loose)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--only')
    ap.add_argument('--no-reads', action='store_true')
    ap.add_argument('--parallel', type=int, default=1)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    state_file = out / 'state.json'
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    api = Api(os.environ.get('LOUPE_LOGIN_FILE', '/root/.config/loupe-jobs/login'))
    only = set(args.only.split(',')) if args.only else None
    lock = threading.Lock()

    def one(theory):
        print(time.strftime('%H:%M:%S'), theory['id'], theory['title'], flush=True)
        try:
            done = run_one(api, theory, state, state_file, lock, reads=not args.no_reads)
        except Exception as exc:  # noqa: BLE001 - one theory's failure is said; the others go on
            print(time.strftime('%H:%M:%S'), theory['id'], 'FAILED', exc, flush=True)
            return
        with lock:
            state[theory['id']] = done
            state_file.write_text(json.dumps(state, indent=1))
        print(time.strftime('%H:%M:%S'), theory['id'], 'finished', flush=True)

    with ThreadPoolExecutor(max(1, args.parallel)) as pool:
        list(pool.map(one, [t for t in THEORIES if not only or t['id'] in only]))
    rows = [score(api, t, state[t['id']]) for t in THEORIES if t['id'] in state and state[t['id']].get('entry')]
    planted = [r for r in rows if not r['control']]
    cost = sum((state[r['id']].get('sweep') or {}).get('cost', {}).get('usd', 0) for r in rows)
    calls = sum((state[r['id']].get('sweep') or {}).get('cost', {}).get('calls', 0) for r in rows)
    summary = dict(theories=len(rows), caught=sum(1 for r in planted if r['caught']), with_planted=len(planted),
                   items_cited=sum(r['planted_cited'] for r in planted), items_planted=sum(r['planted'] for r in planted),
                   proposals=sum(r['proposals'] for r in rows), not_on_planted=sum(len(r['not_on_planted']) for r in rows),
                   control_proposals=sum(r['proposals'] for r in rows if r['control']),
                   watermark=sum(1 for r in rows for x in r['not_on_planted'] if x['watermark']), usd=round(cost, 4), calls=calls, rows=rows)
    (out / 'result.json').write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}))
    for r in rows:
        print(r['id'], 'planted', r['planted'], 'cited', r['planted_cited'], 'proposals', r['proposals'], 'loose', len(r['not_on_planted']))


if __name__ == '__main__':
    sys.exit(main())
