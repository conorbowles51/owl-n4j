#!/usr/bin/env bash
# Hourly health of every store's backup. Each store's own check alerts through BACKUP_ALERT_CMD; this collects them
# into one file the status board reads, so a failed or stale backup shows even when an alert was already sent.
#
#   backup-check.sh          write STATUS_FILE (store <tab> state <tab> detail <tab> checked at); exit 1 if any failed
#
# States: ok, FAILED, and OFF for the evidence copy until a destination is set in EVIDENCE_COPY_DEST. OFF is a real gap
# and shows on the board as one, but sends no alert: it waits on a decision, and an hourly alert would not change that.
# Install: see the header of deploy/owl-backup-check.service.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_NAME=backup-check
. "${HERE}/backup-lib.sh"
STATUS_FILE="${STATUS_FILE:-/mnt/owl-data/backups/status.tsv}"
EVIDENCE_COPY_DEST="${EVIDENCE_COPY_DEST:-}"
EVIDENCE_COPY_MAX_AGE_HOURS="${EVIDENCE_COPY_MAX_AGE_HOURS:-73}"
PY="${PY:-python3}"

tmp="$(mktemp "${STATUS_FILE}.XXXXXX")" || exit 1
failed=0
at="$(date -u -d "@$(now)" +%FT%TZ)"

record() { printf '%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "${at}" >> "${tmp}"; }

store() {  # <label> <command...>
    local label="$1" out; shift
    if out="$("$@" 2>&1)"; then
        record "${label}" ok "$(printf '%s\n' "${out}" | tail -n 1 | sed 's/^[^ ]* [^ ]*: //')"
    else
        record "${label}" FAILED "$(printf '%s\n' "${out}" | grep -m1 'ALERT:' | sed 's/.*ALERT: //' | cut -c1-240)"
        failed=$(( failed + 1 ))
    fi
}

evidence_copy() {
    if [[ -z "${EVIDENCE_COPY_DEST}" ]]; then
        record evidence-copy OFF "no second location set: evidence files have no copy off their disk"
        return
    fi
    local reason
    if reason="$("${PY}" -I - "${EVIDENCE_COPY_DEST}/last-run.json" "$(now)" "${EVIDENCE_COPY_MAX_AGE_HOURS}" 2>&1 <<'PY'
import calendar, json, sys, time
path, now, limit = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
try:
    run = json.load(open(path))
except OSError:
    sys.exit("evidence copy has never finished a run")
age = (now - calendar.timegm(time.strptime(run["finished"], "%Y-%m-%dT%H:%M:%SZ"))) // 3600
if age >= limit:
    sys.exit(f"evidence copy last ran {age} h ago (limit {limit} h)")
if run["tally"]["failed"] or run["errors_total"]:
    sys.exit(f"evidence copy: {run['errors_total']} errors in the last run; first: {(run['errors'] or ['?'])[0]}"[:200])
if run.get("stopped") == "space":
    sys.exit("evidence copy stopped: the free-space floor was reached, new files are not being copied")
since = run.get("last_complete") or run.get("first_started") or run["finished"]
behind = (now - calendar.timegm(time.strptime(since, "%Y-%m-%dT%H:%M:%SZ"))) // 3600
if behind >= 168:
    sys.exit(f"evidence copy has not finished a whole pass in {behind} h")
print(f"{run['files_in_copy']} files, {run['bytes_in_copy']} bytes, last run {age} h ago, complete={run['complete']}")
PY
    )"; then
        record evidence-copy ok "${reason}"
    else
        alert "${reason}"
        record evidence-copy FAILED "${reason}"
        failed=$(( failed + 1 ))
    fi
}

store postgres bash "${HERE}/db-backup.sh" check
store neo4j bash "${HERE}/neo4j-backup.sh" check
store chroma bash "${HERE}/chroma-backup.sh" check
store keys bash "${HERE}/keys-bundle.sh" check
store restore-drill bash "${HERE}/restore-drill.sh" check
evidence_copy
chmod 644 "${tmp}"
mv -f -- "${tmp}" "${STATUS_FILE}"
exit $(( failed > 0 ))
