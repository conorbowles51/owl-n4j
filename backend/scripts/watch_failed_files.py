"""The status board's "Failed files" section and the coordinator's failed-files alerts (lx-chunking, 8 Nov 2026).

'SB4 - Pop & Locke' had 250 files failed for 11 days and nothing reported them. Each run:
- writes the board section: per case, failed files counted by plain reason, and the oldest time a failure was seen;
- tells the coordinator (FYI line in its inbox) when a case gained 10 or more failed files within an hour, and when
  the engine refused a whole request (its "request-refused POST /cases/<id>/files" log line), once each.
Selects by status = 'failed' (services/evidence_failures). State (first-seen times, alerts sent) is a JSON file.
    set -a; . <app>/.env; set +a; PYTHONPATH=. python scripts/watch_failed_files.py --board <md> --state <json>
"""
import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

TELL = "/mnt/owl-data/fin-wt/headless/tell.sh"
GAIN_ALERT = 10
HOUR = 3600
REFUSAL = re.compile(r"request-refused POST /cases/([0-9a-f-]{36})/files 4\d\d: (.*)")


def _stamp(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def evaluate(rows, titles: dict, state: dict, now: float, refusal_lines: list[str]):
    """Pure: (board lines, alert sentences, new state) from the failed rows and the engine's refusal log lines."""
    from services import evidence_failures
    baseline_at = state.get("baseline_at", now)  # the first run sees old failures: it alerts nothing about them
    prior = dict(state.get("first_seen") or {})
    current = {str(file_id): str(case_id) for file_id, case_id, _ in rows}
    seen = {file_id: prior.get(file_id, now) for file_id in current}
    alerted = {case: at for case, at in (state.get("gain_alerted") or {}).items() if now - at < HOUR}
    alerts = []
    gained = Counter(case for file_id, case in current.items()
                     if seen[file_id] > baseline_at and now - seen[file_id] < HOUR)
    for case, count in gained.items():
        if count >= GAIN_ALERT and case not in alerted:
            alerts.append(f"{titles.get(case, case)}: {count} files failed in the last hour. "
                          f"Reasons: {'; '.join(evidence_failures.report_lines(evidence_failures.reasons_by_case([r for r in rows if str(r[1]) == case])[case]))[:600]}")
            alerted[case] = now
    refused = Counter()
    reason_of = {}
    for line in refusal_lines:
        match = REFUSAL.search(line)
        if match:
            refused[match.group(1)] += 1
            reason_of[match.group(1)] = match.group(2)[:200]
    for case, count in refused.items():
        alerts.append(f"{titles.get(case, case)}: the processing engine refused {count} whole request(s) of files "
                      f"(reason: {reason_of[case]}). The backend splits a refused request until only the refused "
                      f"file fails; check the case's failed files.")
    board = []
    by_case = evidence_failures.reasons_by_case(rows)
    for case, counts in sorted(by_case.items(), key=lambda item: -sum(item[1].values())):
        oldest = min(seen[f] for f, c in current.items() if c == case)
        when = (f"oldest failed before the watch began at {_stamp(baseline_at)}" if oldest <= baseline_at
                else f"oldest seen failed {_stamp(oldest)}")
        board.append(f"- **{titles.get(case, case)}**: {sum(counts.values())} failed ({when}): "
                     + "; ".join(evidence_failures.report_lines(counts)))
    return board or ["- none"], alerts, {"first_seen": seen, "gain_alerted": alerted, "baseline_at": baseline_at}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--engine-container", default="owl-v2-evidence-api")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    from postgres.models.case import Case
    from postgres.session import _get_session_local
    from services import evidence_failures

    state = json.loads(args.state.read_text()) if args.state.exists() else {}
    now = time.time()
    since = int(state.get("logs_read_to") or now - 900)
    try:
        logs = subprocess.run(["docker", "logs", "--since", str(since), "--until", str(int(now)),
                               args.engine_container], capture_output=True, text=True, timeout=30)
        refusal_lines = [l for l in (logs.stdout + logs.stderr).splitlines() if "request-refused POST" in l]
    except Exception as exc:  # the board still says what is failed
        print(f"engine log not read: {exc}", file=sys.stderr)
        refusal_lines = []
    with _get_session_local()() as db:
        rows = evidence_failures.failed_files(db)
        titles = {str(c.id): c.title for c in db.query(Case).filter(Case.id.in_({r[1] for r in rows} | {
            __import__("uuid").UUID(m.group(1)) for m in map(REFUSAL.search, refusal_lines) if m})).all()}
    board, alerts, new_state = evaluate(rows, titles, state, now, refusal_lines)
    new_state["logs_read_to"] = int(now)
    if args.dry_run:
        print("\n".join(board)); print("\n".join(f"ALERT {a}" for a in alerts))
        return 0
    for alert in alerts:
        result = subprocess.run([TELL, "fyi", "coordinator", "failed-files", alert], capture_output=True, text=True,
                                timeout=30)
        if result.returncode != 0:
            print(f"tell failed: exit {result.returncode}", file=sys.stderr)
    args.board.write_text("\n".join(board) + "\n")
    args.state.write_text(json.dumps(new_state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
