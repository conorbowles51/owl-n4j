"""lx-matchgrades E: read-only live counts of what the other fixed numbers leave out (A6, A8, A10, A11b)."""
import sys, json, time
sys.path.insert(0, '.')
from collections import Counter
from sqlalchemy import text
from postgres.session import _get_engine
PHONES = ['d9945277-6c80-4a39-82c7-93a95d420384', '4aa79795-1076-4c75-985f-784936abb71f', '574a9752-7d19-4f42-8f98-2112615f4a48',
          '88e01b57-d472-452a-b103-b694292ed012', '7006c0ab-9c93-473a-900a-76d06d9d0603']
def count_results(res):
    return Counter(r.get('kind') for r in res)
with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    # A10: stored identifiers the cross-case index can never match (definition rows)
    a10 = dict(c.execute(text("SELECT count(*) FILTER (WHERE length(identifier_normalised) BETWEEN 1 AND 5) short, count(*) FILTER (WHERE length(identifier_normalised) >= 6) ok, count(*) FILTER (WHERE identifier_normalised IS NULL OR identifier_normalised = '') none FROM financial_accounts")).one()._mapping)
    a10h = dict(c.execute(text("SELECT count(*) FILTER (WHERE kind IN ('account','app_user','other') AND length(value_normalised) < 3) short, count(*) total FROM phone_identities")).one()._mapping)
    print(json.dumps(dict(row='A10', accounts=a10, handles=a10h)), flush=True)
    from services.phone_analysis import approaches
    approaches.install()
    from services.phone_analysis import message_reconciliation as MR, number_switching as NS, framework as F
    for case in PHONES:
        out = dict(case=case)
        try:
            t = time.time(); base, cb = MR.analyse(c, case, F.validate_parameters(MR, {}))
            b0 = dict(MR.last_counts()) if hasattr(MR, 'last_counts') else {}
            mb, mo = MR.MIN_BODY, MR.MAX_OCCURRENCES
            MR.MIN_BODY, MR.MAX_OCCURRENCES = 0, 10 ** 9
            wide, cw = MR.analyse(c, case, F.validate_parameters(MR, {}))
            MR.MIN_BODY, MR.MAX_OCCURRENCES = mb, mo
            out['A6_default'] = dict(count_results(base)); out['A6_no_min_body_or_occurrence'] = dict(count_results(wide))
            out['A6_sec'] = round(time.time() - t, 1)
        except Exception as e:
            out['A6_error'] = repr(e)[:200]
        try:
            base, cb = NS.analyse(c, case, F.validate_parameters(NS, {}))
            k0 = dict(NS.last_counts())
            wide, cw = NS.analyse(c, case, {"gap_days": 14, "window_days": 90, "threshold": 0.0, "min_shared": 0})
            k1 = dict(NS.last_counts())
            out['A8_default'] = dict(results=len(base), counts=k0); out['A8_threshold0_min_shared0'] = dict(results=len(wide), counts=k1)
        except Exception as e:
            out['A8_error'] = repr(e)[:200]
        print(json.dumps(out, default=str), flush=True)
    c.rollback()
