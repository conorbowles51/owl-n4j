"""Add one clearly synthetic case event to the synthetic network fixture, once."""
import json
from pathlib import Path
from uuid import uuid4
from neo4j import GraphDatabase
ROOT=Path(__file__).resolve().parents[1]
report=ROOT/'data/local-runtime/financial-context-fixture.json'
if report.exists():raise RuntimeError('Context fixture already exists; do not rerun.')
case=json.loads((ROOT/'data/local-runtime/network-review-check.json').read_text())['case_id']
key=str(uuid4())
with GraphDatabase.driver('bolt://127.0.0.1:57687',auth=('neo4j','loupe_local_dev')) as driver:
    with driver.session() as session:
        session.run('CREATE (n:Meeting {key:$key, case_id:$case, name:$name, date:$date, summary:$summary})',key=key,case=case,name='SYNTHETIC — discussion of transfer',date='2026-01-02',summary='Synthetic context only. Temporal proximity does not establish a payment connection.').consume()
report.write_text(json.dumps(dict(case_id=case,event_key=key,synthetic=True),indent=2))
print(report)
