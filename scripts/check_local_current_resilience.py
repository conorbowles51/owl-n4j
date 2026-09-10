"""Fresh, guarded current-schema candidate save/finalization concurrency check.

Leaves one labelled synthetic case; preserves older acceptance reports.
"""
from pathlib import Path
from check_local_candidate_materialization import main
root=Path(__file__).resolve().parents[1]
fixture="current-resilience-fixture.json"
result="current-resilience-check.json"
if any((root/"data/local-runtime"/name).exists() for name in (fixture,result)):
    raise SystemExit("This synthetic journey already started. Inspect its report; do not recreate it.")
main(fixture_report=fixture,result_report=result)
