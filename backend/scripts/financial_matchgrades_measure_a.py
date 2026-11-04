"""lx-matchgrades A: read-only counts of what the transfer and matched-payment cutoffs leave out, per case."""
import sys, json, time, bisect
sys.path.insert(0, '.')
from collections import Counter, defaultdict
from datetime import date
from sqlalchemy import text
from sqlalchemy.orm import Session
from postgres.session import _get_engine
CASES = sys.argv[1:] or ['d5b330d1-b3fe-4b03-8539-98d9cc3115e0', '49494305-dcd5-4821-8937-d99cfec3abd9',
    '5eeaa265-5e14-4c96-9710-3135bd9e68ce', '267842f3-32d9-467c-85f8-5e1cc3a28cd8',
    '1c75e65e-d28d-4de2-8eb1-0c03b218700e', 'd9945277-6c80-4a39-82c7-93a95d420384']
BUCKETS = [(0, 3), (4, 7), (8, 14), (15, 31), (32, 90), (91, 365), (366, 10**6)]
def bucket(g):
    for lo, hi in BUCKETS:
        if lo <= g <= hi: return '%d-%d' % (lo, hi)
def main():
    from services.financial import payment_party_matches as P
    from services.financial.linkage import name_similarity
    eng = _get_engine()
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        s = Session(bind=c)
        for case in CASES:
            t0 = time.time()
            rows = P.case_rows(s, case)
            t1 = time.time()
            found = P.match_parties(rows); printed = P.printed_accounts(rows, frozenset(found))
            t2 = time.time()
            by = defaultdict(list)
            for r in rows:
                if r['ordering_date']:
                    by[(r['currency'], int(r['amount_minor']))].append(r)
            gaps = Counter(); partners = Counter(); unnamed_with = Counter(); name_hi = Counter()
            for key, b in by.items():
                deb = [r for r in b if r['direction'] == 'debit']; cre = sorted([r for r in b if r['direction'] == 'credit'], key=lambda r: r['ordering_date'])
                if not deb or not cre: continue
                ds = [r['ordering_date'] for r in cre]
                for d in deb:
                    for cr in cre:
                        if cr['account_id'] == d['account_id']: continue
                        g = abs((cr['ordering_date'] - d['ordering_date']).days)
                        bk = bucket(g); gaps[bk] += 1; partners[d['id']] += 1; partners[cr['id']] += 1
                        if not d.get('name') or not cr.get('name'): unnamed_with[bk] += 1
                        if g <= 14:
                            sims = [x for x in (name_similarity(d.get('name'), cr['holder']), name_similarity(cr.get('name'), d['holder'])) if x is not None]
                            sim = min(sims) if sims else None
                            name_hi['none' if sim is None else ('>=0.85' if sim >= 0.85 else ('0.5-0.85' if sim >= 0.5 else '<0.5'))] += 1
            pc = sorted(partners.values())
            out = dict(case=case, rows=len(rows), named_by_match=len(found), named_by_printed=len(printed),
                       pairs_exact_amount_by_gap=dict(gaps), pairs_with_an_unnamed_side_by_gap=dict(unnamed_with),
                       pairs_le14_by_name_similarity=dict(name_hi), rows_in_any_pair=len(pc),
                       max_partners=pc[-1] if pc else 0, p99_partners=pc[int(len(pc)*.99)] if pc else 0,
                       sec_rows=round(t1-t0, 2), sec_match=round(t2-t1, 2), sec_pairs=round(time.time()-t2, 2))
            print(json.dumps(out, default=str), flush=True)
        c.rollback()
main()
