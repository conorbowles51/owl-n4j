#!/usr/bin/env bash
# Check the customer-instance inventory: every entry has the required fields and the
# entry for the box this runs on is fresh (a stale entry means the per-head scans, and
# with them this inventory, stopped running). Exit 0 clean; 1 with each problem listed.
# Usage: inventory-check.sh [<inventory-dir>] [<max-age-hours>]
set -euo pipefail
cd "$(dirname "$0")"
. ./ci-lib.sh

inv="${1:-$CI_REPORTS_DIR/inventory}"
max_age_h="${2:-48}"

python3 - "$inv" "$max_age_h" <<'EOF'
import json, glob, os, sys
from datetime import datetime, timezone
inv, max_age_h = sys.argv[1], int(sys.argv[2])
required = ["customer", "region", "version", "health", "backup_state", "last_deployment"]
problems = []
entries = sorted(glob.glob(os.path.join(inv, "*.json")))
if not entries:
    problems.append(f"no inventory entries in {inv}")
for p in entries:
    name = os.path.basename(p)
    try:
        e = json.load(open(p))
    except Exception as ex:
        problems.append(f"{name}: unreadable ({ex})")
        continue
    for f in required:
        if f not in e or e[f] in ("", None):
            problems.append(f"{name}: missing field {f}")
    w = e.get("written")
    if w:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(w)).total_seconds() / 3600
            if age > max_age_h:
                problems.append(f"{name}: stale, written {age:.0f}h ago (limit {max_age_h}h)")
        except Exception as ex:
            problems.append(f"{name}: bad written timestamp ({ex})")
for pr in problems:
    print(f"PROBLEM: {pr}")
print(f"{len(entries)} entries, {len(problems)} problems")
sys.exit(1 if problems else 0)
EOF
