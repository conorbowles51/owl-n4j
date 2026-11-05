#!/usr/bin/env bash
# Daily: every live evidence row that names a file still has it (backend/services/evidence_file_check.py). Called hourly
# from backup-check.sh, whose board line and alerts it shares, and runs the real check once in EVIDENCE_CHECK_HOURS; in
# between it repeats the last result. A newly missing row or a refused check alerts through BACKUP_ALERT_CMD and the
# rows then show as missing in the app. A check that could not finish keeps no result, so the next hour tries again.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_NAME=evidence-file-check
. "${HERE}/backup-lib.sh"
STATE_FILE="${EVIDENCE_CHECK_STATE:-/mnt/owl-data/backups/evidence-file-check.last}"
EVIDENCE_CHECK_HOURS="${EVIDENCE_CHECK_HOURS:-23}"
BACKEND_DIR="${BACKEND_DIR:-$(dirname "${LIVE_CHECKOUT}")/loupe-backend/current/backend}"
PY="${EVIDENCE_CHECK_PY:-${LIVE_CHECKOUT}/.venv/bin/python}"

if [[ -s "${STATE_FILE}" ]] && (( $(now) - $(stat -c %Y "${STATE_FILE}") < EVIDENCE_CHECK_HOURS * 3600 )); then
    tail -n 1 "${STATE_FILE}"
    exit 0
fi

out="$(cd "${BACKEND_DIR}" && PYTHONDONTWRITEBYTECODE=1 "${PY}" -m scripts.evidence_file_check check 2>&1)"
rc=$?
while IFS= read -r reason; do alert "${reason#ALERT: }"; done < <(printf '%s\n' "${out}" | grep '^ALERT: ')
if (( rc == 0 || rc == 1 )); then
    printf '%s\n' "${out}" | tail -n 1 > "${STATE_FILE}.tmp" && touch -d "@$(now)" "${STATE_FILE}.tmp" \
        && mv -f -- "${STATE_FILE}.tmp" "${STATE_FILE}"
fi
if (( rc == 0 )); then log "ok: ${out##*$'\n'}"; exit 0; fi
if [[ -z "${ALERTED:-}" ]]; then alert "evidence file check stopped (exit ${rc}): $(printf '%s\n' "${out}" | tail -n 1 | cut -c1-200)"; fi
exit 1
