#!/usr/bin/env bash
# The daily evidence file check's wrapper, with a fake backend: once a day, an alert on a new row, a retry after a stop.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root:?}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "${test_root}/backend"
cat > "${test_root}/fake-python" <<PY
#!/usr/bin/env bash
echo run >> "${test_root}/runs"
cat "${test_root}/out"
exit \$(cat "${test_root}/rc")
PY
chmod +x "${test_root}/fake-python"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$1" >> %q\n' "${test_root}/alerts" > "${test_root}/alert"; chmod +x "${test_root}/alert"
fail() { echo "FAIL: $*"; exit 1; }
runs() { [[ -f "${test_root}/runs" ]] && wc -l < "${test_root}/runs" || echo 0; }
now=$(date -u -d '2026-11-05 12:00' +%s)
go() { env NOW_EPOCH="${now}" EVIDENCE_CHECK_STATE="${test_root}/state" BACKEND_DIR="${test_root}/backend" EVIDENCE_CHECK_PY="${test_root}/fake-python" \
    BACKUP_ALERT_CMD="${test_root}/alert" bash "${source_dir}/evidence-file-check.sh"; }
printf 'ok: 10 rows checked, 0 have no file, 0 new, 0 back\n' > "${test_root}/out"; echo 0 > "${test_root}/rc"

line="$(go)" || fail "clean run failed"
[[ "${line}" == *"ok: 10 rows checked"* ]] || fail "summary not printed: ${line}"
[[ ! -e "${test_root}/alerts" ]] || fail "alerted on a clean run"
go > /dev/null || fail "repeat failed"
[[ "$(runs)" == 1 ]] || fail "checked twice inside a day: $(runs)"

# A day on, one row newly gone: one alert, and FAILED this hour with the reason on the board.
now=$(( now + 86400 ))
printf 'ALERT: 1 evidence rows newly have no file on disk: case abcd1234 (1). They now show as missing in the app\nok: 10 rows checked, 1 have no file, 1 new, 0 back\n' > "${test_root}/out"
echo 3 > "${test_root}/rc"
if out="$(go)"; then fail "new row exited 0"; fi
grep -q 'ALERT: 1 evidence rows' <<<"${out}" || fail "the reason is not in the output backup-check reads"
[[ "$(grep -c 'case abcd1234' "${test_root}/alerts")" == 1 ]] || fail "no single alert"
go > /dev/null || fail "the next hour repeats the last result"
[[ "$(runs)" == 2 ]] || fail "new row rechecked inside the day"

# A refusal keeps no result: the next hour runs again and alerts again.
now=$(( now + 86400 ))
printf 'ALERT: evidence file check refused: 900 of 1000 rows are newly missing\n' > "${test_root}/out"; echo 2 > "${test_root}/rc"
rm -f "${test_root}/alerts"
if go > /dev/null; then fail "refusal exited 0"; fi
grep -q 'refused' "${test_root}/alerts" || fail "refusal not alerted"
if go > /dev/null; then fail "refusal exited 0 on the retry"; fi
[[ "$(runs)" == 4 ]] || fail "refusal was not retried: $(runs)"

# A crash (Python exits 1: the release moved the code, say) says it stopped, keeps no result and is tried again.
now=$(( now + 86400 ))
printf 'Traceback\nNo module named scripts.evidence_file_check\n' > "${test_root}/out"; echo 1 > "${test_root}/rc"; rm -f "${test_root}/alerts"
before="$(runs)"
if go > /dev/null; then fail "crash exited 0"; fi
grep -q 'stopped (exit 1): No module named' "${test_root}/alerts" || fail "crash not alerted"
if go > /dev/null; then fail "a crash was remembered as a result"; fi
[[ "$(runs)" == $(( before + 2 )) ]] || fail "crash was not retried"
echo "test-evidence-file-check: all passed"
