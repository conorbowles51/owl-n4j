"""lx-matchgrades B/C: read-only, per financial case. Names shown today (dumped for a live-vs-branch diff), transfer
pairs the workbench default (3 days) offers, and every possible pair graded by strength; other-leg candidates for
unnamed payments by strength. Usage: <out.json> [case ...]"""
import sys, json, time
sys.path.insert(0, '.')
from collections import Counter
from dataclasses import replace
from sqlalchemy import text
from sqlalchemy.orm import Session
from postgres.session import _get_engine
from postgres.models.enums import LinkRelation
OUT = sys.argv[1]
CASES = sys.argv[2:] or ['d5b330d1-b3fe-4b03-8539-98d9cc3115e0', '49494305-dcd5-4821-8937-d99cfec3abd9',
    '5eeaa265-5e14-4c96-9710-3135bd9e68ce', '267842f3-32d9-467c-85f8-5e1cc3a28cd8',
    '1c75e65e-d28d-4de2-8eb1-0c03b218700e', 'd9945277-6c80-4a39-82c7-93a95d420384']
from services.financial import payment_party_matches as P
from services.financial import linkage as L
print(P.__file__, file=sys.stderr)
graded_on = hasattr(L, 'graded_transfer_pairs')
res = {}
with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY")); s = Session(bind=c)
    for case in CASES:
        t0 = time.time(); names = P.case_party_matches(s, case); t1 = time.time()
        row = dict(names={k: [v['value'], v.get('matched_transaction_id') or v.get('matched_account_id')] for k, v in sorted(names.items())},
                   names_count=len(names), sec_names=round(t1 - t0, 2))
        rows = [r for r in P.case_rows(s, case) if r['ordering_date']]
        obs = [replace(P._observation(r), counterparty_raw=r.get('name') or None, holder_name=r.get('holder') or None) for r in rows]
        t2 = time.time(); comp = L.link_composite(obs, tolerance_days=3)
        cp = [l for l in comp.links if l.relation is LinkRelation.counterparty]
        row['before_workbench_default_3d'] = dict(Counter(l.outcome.value for l in cp)); row['sec_composite'] = round(time.time() - t2, 2)
        if graded_on:
            by_id = {r['id']: r for r in rows}
            t3 = time.time()
            g = L.graded_transfer_pairs(obs, per_row=50, same_holder=lambda d, cc: P._related_holders(by_id[str(d.transaction_id)]['holder'], by_id[str(cc.transaction_id)]['holder']))
            row['sec_graded'] = round(time.time() - t3, 2)
            row['after_graded_by_level'] = g['by_level']; row['after_left_out'] = g['left_out']
            row['after_graded_within_3d_by_level'] = dict(Counter(p['level'] for p in g['pairs'] if p['gap_days'] <= 3))
            from services.match_strength import rank
            offered = Counter(); payments = set()
            for p in g['pairs']:
                for me, ot in ((p['debit_id'], p['credit_id']), (p['credit_id'], p['debit_id'])):
                    m = by_id[me]
                    if m.get('name') or me in names:
                        continue
                    lv = p['level']
                    if P.compatible(m, by_id[ot]) and rank(lv) < rank('weak'):
                        lv = 'weak'
                    offered[lv] += 1; payments.add(me)
            row['after_other_leg_candidates_for_unnamed_by_level'] = dict(offered)
            row['unnamed_payments_with_a_candidate'] = len(payments)
        res[case] = row
        print(json.dumps({k: v for k, v in row.items() if k != 'names'} | {'case': case}), flush=True)
    c.rollback()
json.dump(res, open(OUT, 'w'), indent=1, default=str)
