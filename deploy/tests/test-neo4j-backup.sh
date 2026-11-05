#!/usr/bin/env bash
# Neo4j daily dump: a fake docker stands in for the live and scratch containers, a temp tree for the store.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root:?}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
script="${source_dir}/neo4j-backup.sh"
dir="${test_root}/backups"; store="${test_root}/store"; state="${test_root}/state"; alerts="${test_root}/alerts"
mkdir -p "${state}" "${store}"/databases/{neo4j,system} "${store}"/transactions/{neo4j,system} "${store}/dbms"
echo x > "${store}/databases/neo4j/neostore"; echo x > "${store}/databases/system/neostore"; echo 1 > "${store}/server_id"
echo 1 > "${store}/transactions/neo4j/checkpoint.0"; echo 1 > "${store}/transactions/system/checkpoint.0"
echo log > "${store}/transactions/neo4j/neostore.transaction.db.1"; echo a > "${store}/dbms/auth"
fake="${test_root}/docker"
cat > "${fake}" <<'EOF'
#!/usr/bin/env bash
# FAKE_STATE/live, /scratch: counts each side answers. FAKE_STATE/nostart: the scratch never recovers.
s="${FAKE_STATE}"
case "$1" in
    inspect)
        if [[ "$*" == *Running* ]]; then [[ -f "${s}/nostart" ]] && echo false || echo true; else echo sha256:img; fi ;;
    rm|stop) ;;
    run)
        if [[ "$*" == *"-d "* ]]; then echo id; exit 0; fi
        for a in "$@"; do [[ "${a}" == *":/out" ]] && out="${a%%:*}"; [[ "${a}" == neo4j || "${a}" == system ]] && db="${a}"; done
        [[ -f "${s}/nodump" ]] && exit 1
        size=4000; [[ -f "${s}/smalldump" ]] && size=10
        head -c "${size}" /dev/zero > "${out}/${db}.dump" ;;
    exec)
        if [[ "$*" == *"owl-live"* ]]; then
            cat > /dev/null; echo 'c, nodes, rels'
            n="$(cat "${s}/live.n" 2>/dev/null || echo 0)"; echo $(( n + 1 )) > "${s}/live.n"
            sed -n "$(( n + 1 ))p" "${s}/live" | grep . || tail -n 1 "${s}/live"
        else
            q="$(cat)"
            [[ "${q}" == *"RETURN 1"* ]] && { [[ -f "${s}/nostart" ]] && exit 1; exit 0; }
            echo 'c, nodes, rels'; cat "${s}/scratch"
        fi ;;
esac
EOF
chmod +x "${fake}"
# The copy of the transaction logs is where a live checkpoint lands: each one takes the next line of FAKE_STATE/checkpoints.
cat > "${test_root}/cp" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *transactions/neo4j* && -s "${FAKE_STATE}/checkpoints" ]]; then
    head -n 1 "${FAKE_STATE}/checkpoints" > "${FAKE_STORE}/transactions/neo4j/checkpoint.0"; sed -i 1d "${FAKE_STATE}/checkpoints"
fi
exec /bin/cp "$@"
EOF
chmod +x "${test_root}/cp"
alert_cmd="${test_root}/alert"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$1" >> %q\n' "${alerts}" > "${alert_cmd}"; chmod +x "${alert_cmd}"
run() {  # <now-epoch> <dump|check>
    env PATH="${test_root}:${PATH}" BACKUP_DIR="${dir}" DOCKER="${fake}" FAKE_STATE="${state}" FAKE_STORE="${store}" BACKUP_ALERT_CMD="${alert_cmd}" \
        NEO4J_DATA="${store}" NEO4J_CONTAINER=owl-live LIVE_CHECKOUT="${test_root}" MEM_WAIT_S=0 MEM_FLOOR_MB=0 \
        READY_TRIES=2 READY_SLEEP=0 NOW_EPOCH="$1" bash "${script}" "$2" >> "${test_root}/log" 2>&1
}
fail() { echo "FAIL: $*"; echo "--- log"; cat "${test_root}/log"; exit 1; }
epoch() { date -u -d "$1" +%s; }
count() { find "${dir}" -maxdepth 1 -type d -name 'neo4j-*Z' | wc -l; }
good='"case-a", 10, 20'
reset() {
    echo "${good}" > "${state}/live"; echo "${good}" > "${state}/scratch"
    rm -f "${state:?}/live.n" "${state:?}/nostart" "${state:?}/nodump" "${state:?}/smalldump" "${state:?}/checkpoints"
    : > "${alerts}"
}

# 1. No set: the check fails and alerts.
reset
if run "$(epoch '2026-11-05 03:00')" check; then fail "check passed with no set"; fi
grep -q "no Neo4j backup" "${alerts}" || fail "no alert for a missing set"

# 2. Copy matches live: a whole set, counts from live, the check passes, no scratch files left.
reset
run "$(epoch '2026-11-05 02:10')" dump || fail "good dump failed"
set1="${dir}/neo4j-20261105-0210Z"
for f in neo4j.dump system.dump counts.tsv meta.env; do [[ -s "${set1}/${f}" ]] || fail "no ${f}"; done
grep -q 'case-a.10.20' "${set1}/counts.tsv" || fail "counts not written"
grep -q 'counts_source=live' "${set1}/meta.env" || fail "counts source not recorded"
ls -A "${dir}" | grep -Eq 'partial|work' && fail "scratch left behind"
[[ "$(stat -c %a "${set1}/neo4j.dump")" == 600 ]] || fail "dump is not mode 600"
run "$(epoch '2026-11-05 12:00')" check || fail "fresh set failed the check"

# 3. 25 h later: stale, alert.
: > "${alerts}"
if run "$(epoch '2026-11-06 03:11')" check; then fail "stale set passed"; fi
grep -q "25 h old" "${alerts}" || fail "no stale alert"

# 4. A recovered copy that lost rows is refused: this is the check the whole method rests on.
reset; echo '"case-a", 9, 20' > "${state}/scratch"
if run "$(epoch '2026-11-05 02:11')" dump; then fail "a copy short of live was accepted"; fi
[[ "$(count)" -eq 1 ]] || fail "short copy became a set"
grep -q "does not match the live counts" "${alerts}" || fail "no alert for a short copy"

# 5. A checkpoint during the copy starts the copy again; a checkpoint every time ends in an alert, no set.
reset; printf '2\n' > "${state}/checkpoints"
run "$(epoch '2026-11-05 02:12')" dump || fail "second try failed"
grep -q 'checkpoint during the copy' "${test_root}/log" || fail "moved checkpoint not noticed"
grep -q 'copy_tries=2' "${dir}/neo4j-20261105-0212Z/meta.env" || fail "second try not recorded"
reset; for i in 1 2 3 4 5 6 7 8; do echo "$(( i + 10 ))"; done > "${state}/checkpoints"
if run "$(epoch '2026-11-05 02:13')" dump; then fail "accepted with a checkpoint in every try"; fi
grep -q "no copy free of a checkpoint" "${alerts}" || fail "no alert when every try saw a checkpoint"

# 6. Writes during every try: the set is still written, marked as counted from the recovered copy.
reset; printf '"case-a", 10, 20\n"case-a", 11, 20\n"case-a", 12, 20\n"case-a", 13, 20\n"case-a", 14, 20\n"case-a", 15, 20\n' > "${state}/live"
echo '"case-a", 12, 20' > "${state}/scratch"
run "$(epoch '2026-11-05 02:14')" dump || fail "dump under writes failed"
grep -q 'counts_source=recovered-copy' "${dir}/neo4j-20261105-0214Z/meta.env" || fail "unstable counts not marked"
grep -q 'case-a.12.20' "${dir}/neo4j-20261105-0214Z/counts.tsv" || fail "recovered counts not kept"

# 7. A copy that does not recover: alert, nothing written.
reset; touch "${state}/nostart"; n="$(count)"
if run "$(epoch '2026-11-05 02:15')" dump; then fail "unrecovered copy accepted"; fi
[[ "$(count)" -eq "${n}" ]] || fail "unrecovered copy became a set"
grep -q "did not recover" "${alerts}" || fail "no alert when the copy did not recover"

# 8. A dump under half the last one is set aside and does not count.
reset; touch "${state}/smalldump"; n="$(count)"
if run "$(epoch '2026-11-05 02:16')" dump; then fail "tiny dump accepted"; fi
[[ "$(count)" -eq "${n}" ]] || fail "tiny dump became a set"
ls -A "${dir}" | grep -q suspect || fail "tiny dump not kept aside"

# 9. Retention: 31 days old goes, 29 stays.
reset
find "${dir}" -mindepth 1 -maxdepth 1 -type d -name '*neo4j-*' -exec rm -rf -- {} +
now9="$(epoch '2026-12-10 02:10')"
name_at() { echo "neo4j-$(date -u -d "@$1" +%Y%m%d-%H%M)Z"; }
for d in 31 29; do mkdir -p "${dir}/$(name_at $(( now9 - d * 86400 )))"; head -c 4000 /dev/zero > "${dir}/$(name_at $(( now9 - d * 86400 )))/neo4j.dump"; done
run "${now9}" dump || fail "dump for retention failed"
[[ ! -d "${dir}/$(name_at $(( now9 - 31 * 86400 )))" ]] || fail "31-day-old set kept"
[[ -d "${dir}/$(name_at $(( now9 - 29 * 86400 )))" ]] || fail "29-day-old set pruned"

# 10. The store is only read.
[[ "$(cat "${store}/databases/neo4j/neostore")" == x ]] || fail "store changed"
echo "test-neo4j-backup: all passed"
