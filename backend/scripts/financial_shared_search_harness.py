"""lx-sharedsearch A: per query, the records each of a module's own free-text filters returns, against what the
shared case search returns for the same words (ids), read-only on the live database.

  bash /mnt/owl-data/fin-wt/live-run.sh <worktree> financial_shared_search_harness [--out FILE]

Old side: the module's own function as it is in this tree (casework(search=), list_dossiers(search=),
notebook list_notes(query_text=)). New side: ``services.case_search.search`` over the area the records are
embedded in (casework), model ranking and rephrasing off (no chat model), every page read. A record the old side
returns and the new side does not is LOST. Queries: the agent's real calls (agent_tool_calls), the judged sets'
casework queries, and words from each case's own titles. No result text is printed, ids and counts only."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, '.')
from sqlalchemy import text  # noqa: E402

CASES = {  # six financial cases (most ledger rows) and the invented demo cases
    'BNB2': 'd5b330d1-b3fe-4b03-8539-98d9cc3115e0', 'OPDMD62': '49494305-dcd5-4821-8937-d99cfec3abd9',
    'OPDMD66': '5eeaa265-5e14-4c96-9710-3135bd9e68ce', 'monday-finance': '267842f3-32d9-467c-85f8-5e1cc3a28cd8',
    'finance-sunday': '1c75e65e-d28d-4de2-8eb1-0c03b218700e',
    'Verification': 'cded78d0-e659-44cc-940d-d8f8c8012760',
    'lx-demo': 'b75f3f2c-ffa1-4260-8fe9-6f5db4e9d4df', 'demo-2': '3f3489a0-b8ee-4e1a-9ec4-83e8ca327d4c'}
_HERE = os.path.dirname(os.path.abspath(__file__))
SETS = [os.path.join(os.path.dirname(os.path.dirname(_HERE)), 'evidence-engine', 'tests', 'relevance', n)
        for n in ('demo-relevance-set.json', 'second-relevance-set.json')]


def read_only(conn):
    if conn.execute(text('SHOW default_transaction_read_only')).scalar() != 'on':
        raise SystemExit('refusing to run: sessions are not read-only (set PGOPTIONS)')


def queries(conn, case_id, name):
    out = {}  # query -> where it came from
    for n in ('get_casework', 'list_dossiers'):
        for (a,) in conn.execute(text("SELECT t.arguments FROM agent_tool_calls t JOIN agent_runs r ON r.id = t.run_id "
                                      "WHERE t.name = :n AND r.case_id = :c"), {'n': n, 'c': case_id}):
            a = a if isinstance(a, dict) else json.loads(a)
            if (a.get('search') or '').strip():
                out.setdefault(a['search'].strip(), 'agent call')
    for p in SETS:
        j = json.load(open(p))
        if j.get('case_id') == case_id:
            for q in j['queries']:
                if q.get('tool') == 'get_casework' or q.get('kind') == 'casework':
                    out.setdefault((q.get('args') or {}).get('search') or (q.get('args') or {}).get('query') or '',
                                   'judged set')
    words = []
    for (t, b) in conn.execute(text("SELECT title, body FROM workspace_entries WHERE case_id = :c AND deleted_at IS NULL "
                                    "ORDER BY id"), {'c': case_id}):
        for w in re.findall(r"[A-Za-zÀ-ÿ]{5,}", "%s" % (t or '')):
            if w.lower() not in [x.lower() for x in words]:
                words.append(w)
    for (t,) in conn.execute(text("SELECT display_name FROM case_profiles WHERE case_id = :c ORDER BY id"), {'c': case_id}):
        for w in re.findall(r"[A-Za-zÀ-ÿ]{4,}", t or ''):
            if w.lower() not in [x.lower() for x in words]:
                words.append(w)
    for w in words[:25]:
        out.setdefault(w, 'case title word')
        if len(w) > 7:
            out.setdefault(w[:6], 'case title word, cut to a stem')
    out.pop('', None)
    return out


def shared_ids(conn, case_id, q, kinds, prefix):
    from services import case_search
    ids, off = [], 0
    while True:
        r = case_search.search(conn, case_id, q, kinds=kinds, rank=False, phrase=False, limit=50, offset=off,
                               use_cache=False)
        for h in r['hits']:
            c = h.get('cite') or ''
            if prefix in c:
                ids.append(re.search(r'entry=([0-9a-f-]{36})', c).group(1))
        if r.get('next_offset') is None:
            return ids
        off = r['next_offset']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='/mnt/owl-data/tmp/shared-search-harness.json')
    ap.add_argument('--cases', default=','.join(CASES))
    a = ap.parse_args()
    import uuid
    from postgres.session import _get_session_local
    from services.agent import casework_tools, case_material_tools
    from services import notebook_service
    res = {}
    with _get_session_local()() as db:
        conn = db.connection()
        read_only(conn)
        for name in a.cases.split(','):
            cid = CASES[name]
            res[name] = {}
            for q, src in queries(conn, cid, name).items():
                u = uuid.UUID(cid)
                rec = {'source': src}
                old = casework_tools.casework(db, u, search=q, limit=50)
                rec['casework_old'] = sorted(i['id'] for i in old['items'])
                rec['casework_old_total'] = old['total_matching']
                rec['casework_new'] = sorted(set(shared_ids(conn, cid, q, ('casework',), 'view=casework')))
                nb = notebook_service.list_notes(db, case_id=u, current_user=None, query_text=q, limit=200)
                rec['notebook_old'] = sorted(str(n['id']) for n in nb['notes'])
                rec['notebook_old_total'] = nb['total']
                dd = case_material_tools.list_dossiers(db, u, search=q, limit=50)
                rec['dossier_old'] = sorted(i['id'] for i in dd['items'])
                res[name][q] = rec
    json.dump(res, open(a.out, 'w'), indent=1)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
