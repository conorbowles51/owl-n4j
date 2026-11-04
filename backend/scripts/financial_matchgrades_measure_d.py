"""lx-matchgrades D: read-only, per phone case: owner candidate tiers, name-only pairs the suggestion rules never make."""
import sys, json
sys.path.insert(0, '.')
from collections import Counter, defaultdict
from sqlalchemy import text
from postgres.session import _get_engine
from services.phone import fold as F
CASES = ['d9945277-6c80-4a39-82c7-93a95d420384', '4aa79795-1076-4c75-985f-784936abb71f', '574a9752-7d19-4f42-8f98-2112615f4a48',
         '88e01b57-d472-452a-b103-b694292ed012', '7006c0ab-9c93-473a-900a-76d06d9d0603', 'cded78d0-e659-44cc-940d-d8f8c8012760']
with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    for case in CASES:
        o = Counter((r[0], r[1]) for r in c.execute(text("SELECT candidate_kind, tier FROM pv_owner_candidate WHERE case_id=:c"), {"c": case}))
        st = Counter(r[0] for r in c.execute(text("SELECT state FROM phone_identity_suggestions WHERE case_id=:c"), {"c": case}))
        sc = Counter(float(r[0]) for r in c.execute(text("SELECT score FROM phone_identity_suggestions WHERE case_id=:c AND state='open'"), {"c": case}))
        ids = {str(r[0]) for r in c.execute(text("SELECT id FROM phone_identities WHERE case_id=:c AND sighting_count>0 AND NOT (kind='other' AND coalesce(subkind,'')='group')"), {"c": case})}
        names = defaultdict(set)
        for i, n in c.execute(text("SELECT identity_id, name FROM pv_identity_name WHERE case_id=:c"), {"c": case}):
            if str(i) in ids and n and F.fold(n): names[F.fold(n)].add(str(i))
        dossiers = {F.fold(n): str(d) for d, n in c.execute(text("SELECT id, display_name FROM case_profiles WHERE case_id=:c"), {"c": case}) if n}
        linked = {str(r[0]): str(r[1]) for r in c.execute(text("SELECT identity_id, dossier_id FROM phone_identity_links WHERE case_id=:c"), {"c": case})}
        pair_name = sum(len(v) * (len(v) - 1) // 2 for v in names.values() if len(v) > 1)
        big = sorted((len(v) for v in names.values()), reverse=True)[:5]
        dossier_name = sum(1 for n, d in dossiers.items() for i in names.get(n, ()) if linked.get(i) != d)
        print(json.dumps(dict(case=case, identities=len(ids), owner_candidates=dict((f"{k}:{t}", v) for (k, t), v in o.items()),
              suggestions_by_state=dict(st), open_scores=dict(sc), name_only_identity_pairs=pair_name, largest_name_groups=big,
              name_only_dossier_pairs=dossier_name, dossiers=len(dossiers))), flush=True)
    c.rollback()
