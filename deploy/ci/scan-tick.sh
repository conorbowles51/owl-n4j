#!/usr/bin/env bash
# Called every watchdog cycle (headless/status.sh), right after the head-suite tick,
# so the scans fire off the same trigger as the head suite: a new `live <sha>` line
# in deploy-now.log. One scan per live head, detached, never two at once. Cheap and
# silent when there is nothing new. Switch off with CI_SCANS=0 in fleet-gate.conf.
set -euo pipefail
cd "$(dirname "$0")"
. ./ci-lib.sh

conf=/mnt/owl-data/fin-wt/headless/fleet-gate.conf
[ -f "$conf" ] && grep -q '^CI_SCANS=0' "$conf" && exit 0

log="${SUITE_DEPLOY_LOG:-/mnt/owl-data/fin-wt/deploy-now.log}"
mkdir -p "$CI_REPORTS_DIR"

exec 9>>"$CI_REPORTS_DIR/.tick.lock"
flock -n 9 || exit 0   # another tick is mid-launch

sha=$(grep -E '^[0-9:TZ-]+ live [0-9a-f]{7,40}[[:space:]]*$' "$log" 2>/dev/null | tail -1 | awk '{print $3}')
[ -n "$sha" ] || exit 0
s12=${sha:0:12}

# Already launched for this head (done or still running): nothing to do.
[ "$(cat "$CI_REPORTS_DIR/.last-launched" 2>/dev/null)" = "$s12" ] && exit 0

# A scan of an older head still running keeps .scan.lock; the child exits at once
# then, .last-launched stays unset for this head, and a later tick retries.
here=$(pwd)
setsid nohup bash -c "
  exec 8>>'$CI_REPORTS_DIR/.scan.lock'
  flock -n 8 || exit 0
  echo '$s12' > '$CI_REPORTS_DIR/.last-launched'
  bash '$here/scan-head.sh' '$sha'
" </dev/null >> "$CI_REPORTS_DIR/tick.log" 2>&1 &
echo "$(date -u +%FT%TZ) tick: scan of $s12 requested" >> "$CI_REPORTS_DIR/tick.log"
