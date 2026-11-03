#!/usr/bin/env bash
# Nightly database dump: a fake docker stands in for the owl-v2-pg container. No real database is touched.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
script="${source_dir}/db-backup.sh"

dir="${test_root}/backups"
mode="${test_root}/mode"
alerts="${test_root}/alerts"
fake="${test_root}/docker"
cat > "${fake}" <<'EOF'
#!/usr/bin/env bash
# exec [-i] <container> <cmd...>
shift; [[ "$1" == "-i" ]] && shift; shift
mode="$(cat "${FAKE_MODE}")"
case "$*" in
    *pg_dump*)
        case "${mode}" in
            fail) echo "pg_dump: error: connection refused" >&2; exit 1 ;;
            garbage) echo "not a dump" ;;
            small) printf 'PGDMP\n' ;;
            *) printf 'PGDMP\n'; head -c 4000 /dev/zero | tr '\0' 'x'; printf '\n' ;;
        esac ;;
    *"pg_restore --list"*)
        if head -c 5 | grep -q PGDMP; then echo "1; 0 0 TABLE DATA public cases owl_us"; else exit 1; fi ;;
    *) echo "unexpected: $*" >&2; exit 9 ;;
esac
EOF
chmod +x "${fake}"
alert_cmd="${test_root}/alert"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$1" >> %q\n' "${alerts}" > "${alert_cmd}"; chmod +x "${alert_cmd}"

run() {  # <now-epoch> <dump|check>
    env BACKUP_DIR="${dir}" DOCKER="${fake}" FAKE_MODE="${mode}" BACKUP_ALERT_CMD="${alert_cmd}" \
        NOW_EPOCH="$1" bash "${script}" "$2" >> "${test_root}/log" 2>&1
}
fail() { echo "FAIL: $*"; echo "--- log"; cat "${test_root}/log"; exit 1; }
count() { find "${dir}" -maxdepth 1 -name 'owl_db-*Z.dump' | wc -l; }
epoch() { date -u -d "$1" +%s; }

# 1. No dump at all: the check fails and alerts.
echo ok > "${mode}"
if run "$(epoch '2026-11-03 21:00')" check; then fail "check passed with no dumps"; fi
grep -q "no scheduled database dump" "${alerts}" || fail "no alert for missing dump"

# 2. A good dump is written under its UTC name, reads back, and the check passes.
run "$(epoch '2026-11-04 01:30')" dump || fail "good dump failed"
[[ -f "${dir}/owl_db-20261104-0130Z.dump" ]] || fail "dump not named by time"
ls -A "${dir}" | grep -q partial && fail "partial left behind"
run "$(epoch '2026-11-04 12:00')" check || fail "fresh dump failed the check"

# 3. 25 h later with no new dump: stale, alert.
: > "${alerts}"
if run "$(epoch '2026-11-05 02:31')" check; then fail "check passed on a 25 h old dump"; fi
grep -q "25 h old" "${alerts}" || fail "no stale alert: $(cat "${alerts}")"

# 4. pg_dump fails: nothing new, nothing pruned, alert.
echo fail > "${mode}"; : > "${alerts}"
if run "$(epoch '2026-11-05 01:30')" dump; then fail "failed pg_dump reported success"; fi
[[ "$(count)" -eq 1 ]] || fail "failed dump changed the dump set"
grep -q "pg_dump of owl_db failed" "${alerts}" || fail "no alert on pg_dump failure"

# 5. A dump that does not read back is discarded.
echo garbage > "${mode}"
if run "$(epoch '2026-11-05 01:31')" dump; then fail "unreadable dump accepted"; fi
[[ "$(count)" -eq 1 ]] || fail "unreadable dump kept"

# 6. A dump under half the previous size is set aside, never replaces or prunes.
echo small > "${mode}"
if run "$(epoch '2026-11-05 01:32')" dump; then fail "truncated dump accepted"; fi
[[ "$(count)" -eq 1 ]] || fail "truncated dump counted as a dump"
ls -A "${dir}" | grep -q 'suspect' || fail "truncated dump not kept aside"

# 7. Retention: 40 nightly dumps -> the 7 newest plus the newest of earlier weeks, at most 4 weeks back.
rm -f "${dir}"/owl_db-* "${dir}"/.owl_db-*
echo ok > "${mode}"
start="$(epoch '2026-09-01 01:30')"
for i in $(seq 0 39); do run $(( start + i * 86400 )) dump || fail "dump ${i} failed"; done
kept="$(find "${dir}" -maxdepth 1 -name 'owl_db-*Z.dump' -printf '%f\n' | sort)"
n="$(echo "${kept}" | wc -l)"
newest="owl_db-$(date -u -d "@$(( start + 39 * 86400 ))" +%Y%m%d-%H%M)Z.dump"
echo "${kept}" | grep -qx "${newest}" || fail "newest dump pruned"
(( n >= 8 && n <= 12 )) || fail "kept ${n} dumps: ${kept}"
oldest_kept="$(echo "${kept}" | head -n 1)"
oldest_epoch="$(date -u -d "${oldest_kept:7:8} ${oldest_kept:16:2}:${oldest_kept:18:2}" +%s)"
(( start + 39 * 86400 - oldest_epoch <= 35 * 86400 )) || fail "kept a dump older than 5 weeks: ${oldest_kept}"

# 8. Hand-made dumps in the same directory are never pruned.
touch "${dir}/owl_db-20261023-1649-pre-pid-d5.dump"
run $(( start + 40 * 86400 )) dump || fail "dump 40 failed"
[[ -f "${dir}/owl_db-20261023-1649-pre-pid-d5.dump" ]] || fail "hand-made dump pruned"

echo "test-db-backup: all passed"
