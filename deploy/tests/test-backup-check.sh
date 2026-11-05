#!/usr/bin/env bash
# The hourly health file: fake store checks beside a copy of the script.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root:?}"' EXIT
export SEAL_DIR="${test_root}/seal"   # never the box's real keys
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cp "${source_dir}/backup-check.sh" "${source_dir}/backup-lib.sh" "${source_dir}/backup-crypt.sh" "${test_root}/"
for s in db-backup neo4j-backup chroma-backup keys-bundle restore-drill; do
    printf '#!/usr/bin/env bash\nif [[ -f %q/break-%s ]]; then echo "now x: ALERT: %s is broken"; exit 1; fi\necho "2026 %s: ok: fine"\n' \
        "${test_root}" "$s" "$s" "$s" > "${test_root}/$s.sh"
done
status="${test_root}/status.tsv"; dest="${test_root}/copy"; mkdir "${dest}"
run() { env STATUS_FILE="${status}" NOW_EPOCH="$(date -u -d '2026-11-05 12:00' +%s)" BACKUP_ALERT_CMD="${test_root}/alert" "$@" bash "${test_root}/backup-check.sh"; }
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$1" >> %q\n' "${test_root}/alerts" > "${test_root}/alert"; chmod +x "${test_root}/alert"
fail() { echo "FAIL: $*"; cat "${status}" 2>/dev/null; exit 1; }
state() { awk -F'\t' -v s="$1" '$1 == s {print $2}' "${status}"; }

# All well, no destination: every store ok, the copy OFF and named as a gap, no alert, exit 0.
run A=1 || fail "healthy run failed"
for s in postgres neo4j chroma keys restore-drill; do [[ "$(state "$s")" == ok ]] || fail "$s not ok"; done
[[ "$(state evidence-copy)" == OFF ]] || fail "copy not OFF"
grep -q 'no copy off their disk' "${status}" || fail "the gap is not said"
[[ "$(state encryption)" == OFF ]] || fail "encryption gap not shown"
grep -q 'dumps are plain at rest' "${status}" || fail "plain dumps not said"
[[ ! -e "${test_root}/alerts" ]] || fail "alerted on OFF"
[[ "$(stat -c %a "${status}")" == 644 ]] || fail "status file unreadable by the board"

# One store failed: FAILED with its reason, exit 1.
touch "${test_root}/break-neo4j-backup"
if run A=1; then fail "exit 0 with a failed store"; fi
[[ "$(state neo4j)" == FAILED ]] || fail "failed store not shown"
grep -q 'neo4j-backup is broken' "${status}" || fail "reason not shown"
rm "${test_root}/break-neo4j-backup"

# Destination set: never run, stale, errors, good.
if run EVIDENCE_COPY_DEST="${dest}"; then fail "copy with no run passed"; fi
grep -q 'never finished' "${status}" || fail "no first-run reason"
mk() { printf '{"finished":"%s","tally":{"failed":%s},"errors_total":%s,"errors":[],"files_in_copy":5,"bytes_in_copy":9,"complete":true}' "$1" "$2" "$2" > "${dest}/last-run.json"; }
mk 2026-11-01T12:00:00Z 0
if run EVIDENCE_COPY_DEST="${dest}"; then fail "stale copy passed"; fi
grep -q 'limit 73 h' "${status}" || fail "no stale reason"
mk 2026-11-05T06:00:00Z 2
if run EVIDENCE_COPY_DEST="${dest}"; then fail "errors passed"; fi
mk 2026-11-05T06:00:00Z 0
run EVIDENCE_COPY_DEST="${dest}" || fail "good copy failed"
# Stopped by the space floor, or no whole pass for a week: FAILED though a run finished recently.
printf '{"finished":"2026-11-05T06:00:00Z","tally":{"failed":0},"errors_total":0,"errors":[],"stopped":"space"}' > "${dest}/last-run.json"
if run EVIDENCE_COPY_DEST="${dest}"; then fail "space stop passed"; fi
grep -q 'free-space floor' "${status}" || fail "no space reason"
printf '{"finished":"2026-11-05T06:00:00Z","tally":{"failed":0},"errors_total":0,"errors":[],"stopped":"budget","first_started":"2026-10-20T06:00:00Z","last_complete":"","files_in_copy":5,"bytes_in_copy":9,"complete":false}' > "${dest}/last-run.json"
if run EVIDENCE_COPY_DEST="${dest}"; then fail "no whole pass in two weeks passed"; fi
grep -q 'not finished a whole pass' "${status}" || fail "no behind reason"
mk 2026-11-05T06:00:00Z 0
run EVIDENCE_COPY_DEST="${dest}" || fail "good copy failed"
[[ "$(state evidence-copy)" == ok ]] || fail "good copy not ok"
# Encryption: a key with no proven custody stays a gap on the board and alerts nobody; proven, it is ok.
bash "${test_root}/backup-crypt.sh" new-key < /dev/null | sed -n '/BEGIN PGP PRIVATE/,/END PGP PRIVATE/p' > "${test_root}/private.asc"
mk 2026-11-05T06:00:00Z 0; run A=1 || fail "run with an unproven key failed"
[[ "$(state encryption)" == OFF ]] || fail "unproven custody shown as ok"
grep -q 'custody not proven' "${status}" || fail "custody gap not said"
bash "${test_root}/backup-crypt.sh" confirm-key < "${test_root}/private.asc" > /dev/null
run A=1 || fail "run with proven custody failed"
[[ "$(state encryption)" == ok ]] || fail "proven custody not ok"
grep -q 'no drill key' "${status}" || fail "missing drill key not said"
# Custody proven but the newest dump has no sealed file: a seal failed. Not ok, and said.
mkdir -p "${test_root}/bk/scheduled"; : > "${test_root}/bk/scheduled/owl_db-20261105-0130Z.dump"
if run BACKUP_ROOT="${test_root}/bk"; then fail "an unsealed newest dump passed"; fi
[[ "$(state encryption)" == FAILED ]] || fail "unsealed newest dump shown as ok"
grep -q 'owl_db-20261105-0130Z.dump is not sealed' "${status}" || fail "the unsealed dump is not named"
echo "test-backup-check: all passed"
