"""Census for agent-phones D: per case, phones, ledger rows, dossiers with linked phone identities, and approach 1
runs. Read only. Usage (via live-run.sh): financial_agent_phones_census.py"""
import sys
sys.path.insert(0, '.')
from sqlalchemy import create_engine, text  # noqa: E402
from postgres.session import _get_engine  # noqa: E402

with _get_engine().connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    rows = c.execute(text(
        "SELECT k.id, k.title, (SELECT count(*) FROM phone_extractions e WHERE e.case_id = k.id) AS phones, "
        "(SELECT count(*) FROM financial_transactions t WHERE t.case_id = k.id) AS txns, "
        "(SELECT count(DISTINCT person_id) FROM pv_identity i WHERE i.case_id = k.id AND person_id IS NOT NULL) AS linked_people, "
        "(SELECT count(*) FROM phone_analysis_runs r WHERE r.case_id = k.id AND r.approach = 'money_signals') AS ms_runs "
        "FROM cases k ORDER BY 3 DESC, 4 DESC")).fetchall()
    for r in rows:
        if r.phones or r.txns:
            print("%s %-45s phones=%d txns=%d linked_people=%d money_signal_runs=%d" % (str(r.id)[:8], (r.title or '')[:45], r.phones, r.txns, r.linked_people, r.ms_runs))
