#!/usr/bin/env bash
# Write this instance's entry in the customer-instance inventory
# (CI_REPORTS_DIR/inventory/<instance>.json). Called after each per-head scan, so
# the entry tracks every release. Terraform-provisioned customers get their entry
# from deploy/provision (local_file on apply); this script covers the box it runs on.
# Fields: customer, region, version, health, backup_state, last_deployment.
set -euo pipefail
cd "$(dirname "$0")"
. ./ci-lib.sh

sha=${1:-$(grep -E '^[0-9:TZ-]+ live [0-9a-f]{7,40}[[:space:]]*$' /mnt/owl-data/fin-wt/deploy-now.log 2>/dev/null | tail -1 | awk '{print $3}')}
inv="$CI_REPORTS_DIR/inventory"
mkdir -p "$inv"

zone=$(curl -fsS -m 5 -H "Metadata-Flavor: Google" \
  "http://169.254.169.254/computeMetadata/v1/instance/zone" 2>/dev/null | awk -F/ '{print $NF}' || echo unknown)

health=$(curl -fsS -m 10 "http://127.0.0.1:8002/health" 2>/dev/null || echo '"unreachable"')

last_dep=$(grep -E '^[0-9:TZ-]+ live [0-9a-f]{7,40}[[:space:]]*$' /mnt/owl-data/fin-wt/deploy-now.log 2>/dev/null | tail -1 | awk '{print $1}')

backup_state="no health file"
bk=/mnt/owl-data/backups/status.tsv
if [ -f "$bk" ]; then
  age_h=$(( ($(date +%s) - $(stat -c %Y "$bk")) / 3600 ))
  # States in the file are ok / FAILED / OFF (deploy/backup-check.sh); count each.
  backup_state=$(awk -F'\t' -v age="$age_h" \
    '{n++; c[$2]++} END{line=n " checks:"; for (s in c) line=line " " c[s] " " s ","; sub(/,$/, "", line); printf "%s; health file %dh old", line, age}' "$bk")
fi

python3 - "$inv/owl-dev.json" "$sha" "$zone" "$last_dep" "$backup_state" <<'EOF' "$health"
import json, sys
from datetime import datetime, timezone
path, sha, zone, last_dep, backup_state = sys.argv[1:6]
health_raw = sys.argv[6] if len(sys.argv) > 6 else '"unreachable"'
try:
    health = json.loads(health_raw)
except Exception:
    health = health_raw
json.dump({
    "customer": "owl-dev (Owl Consultancy Group development/live box)",
    "region": zone,
    "version": sha,
    "health": health,
    "backup_state": backup_state,
    "last_deployment": last_dep,
    "written": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "written_by": "deploy/ci/inventory-update.sh",
}, open(path, "w"), indent=1)
print(f"inventory entry written: {path}")
EOF
