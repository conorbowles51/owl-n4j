#!/usr/bin/env bash
# Nightly database dump: a fake docker stands in for the owl-v2-pg container. No real database is touched.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root}"' EXIT
export SEAL_DIR="${test_root}/seal"   # never the box's real keys
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
    *psql*)
        [[ "${mode}" == nosession ]] && exit 1
        # The snapshot session: answer the export, then one counts line and the end mark, then wait for the quit.
        while IFS= read -r line; do
            case "${line}" in
                *pg_export_snapshot*) echo "00000003-0000002A-1" ;;
                *"__end__"*) [[ "${mode}" == cutcounts ]] && exit 0; printf 'cases\t\t3\nz_rows\tabc\t7\n'; echo __end__ ;;
                '\q') exit 0 ;;
            esac
        done ;;
    *pg_dump*)
        case "${mode}" in
            fail) echo "pg_dump: error: connection refused" >&2; exit 1 ;;
            garbage) echo "not a dump" ;;
            small) printf 'PGDMP\n' ;;
            *) [[ "$*" == *"--snapshot="* ]] && echo "snapshot" >> "${FAKE_MODE}.seen"; printf 'PGDMP\n'; head -c 4000 /dev/zero | tr '\0' 'x'; printf '\n' ;;
        esac ;;
    *"pg_restore --list"*)
        if head -c 5 | grep -q PGDMP; then echo "1; 0 0 TABLE DATA public cases owl_us"; else exit 1; fi ;;
    *) echo "unexpected: $*" >&2; exit 9 ;;
esac
EOF
chmod +x "${fake}"
alert_cmd="${test_root}/alert"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$1" >> %q\n' "${alerts}" > "${alert_cmd}"; chmod +x "${alert_cmd}"

served=1234567890123456789012345678901234567890
printf '{"status":"ok","commit":"%s"}' "${served}" > "${test_root}/health.json"
export BACKUP_HEALTH_URL="file://${test_root}/health.json"
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
[[ -s "${mode}.seen" ]] || fail "pg_dump did not read the session's snapshot"
grep -q "z_rows.abc.7" "${dir}/owl_db-20261104-0130Z.counts.tsv" || fail "no counts file beside the dump"
grep -q "app_commit=${served}" "${dir}/owl_db-20261104-0130Z.meta" || fail "the meta file does not name the served commit"
run "$(epoch '2026-11-04 12:00')" check || fail "fresh dump failed the check"

# 2b. The snapshot session fails, or the counts are cut off: the dump is still written, no counts file, and an alert.
for m in nosession cutcounts; do
    echo "${m}" > "${mode}"; : > "${alerts}"
    run "$(epoch '2026-11-04 02:00')" dump || fail "${m}: dump failed"
    [[ -f "${dir}/owl_db-20261104-0200Z.dump" ]] || fail "${m}: no dump"
    [[ ! -e "${dir}/owl_db-20261104-0200Z.counts.tsv" ]] || fail "${m}: counts file from a failed session"
    grep -q "no counts file" "${alerts}" || fail "${m}: no alert"
    rm -f "${dir}"/owl_db-20261104-0200Z.*
done
echo ok > "${mode}"

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

# 7. Retention is by age: a scheduled dump more than 30 days old is pruned, one 29 days old is kept.
rm -f "${dir}"/owl_db-* "${dir}"/.owl_db-*
echo ok > "${mode}"
now7="$(epoch '2026-12-10 01:30')"
name_at() { echo "owl_db-$(date -u -d "@$1" +%Y%m%d-%H%M)Z.dump"; }
for days in 31 29 20 10 5 3 2 1; do printf 'PGDMP\n' > "${dir}/$(name_at $(( now7 - days * 86400 )))"; done
run "${now7}" dump || fail "dump at day 0 failed"
[[ ! -f "${dir}/$(name_at $(( now7 - 31 * 86400 )))" ]] || fail "31-day-old dump kept"
[[ -f "${dir}/$(name_at $(( now7 - 29 * 86400 )))" ]] || fail "29-day-old dump pruned"
[[ "$(count)" -eq 8 ]] || fail "expected 8 dumps (7 within 30 days + new), got $(count)"
grep -q "prune $(name_at $(( now7 - 31 * 86400 ))) (older than 30 days)" "${test_root}/log" || fail "prune not logged"

# 7b. 40 nightly dumps: exactly the last 31 (ages 0-30 days) remain, newest included.
rm -f "${dir}"/owl_db-*
start="$(epoch '2026-09-01 01:30')"
for i in $(seq 0 39); do run $(( start + i * 86400 )) dump || fail "dump ${i} failed"; done
[[ "$(count)" -eq 31 ]] || fail "kept $(count) of 40 nightly dumps, expected 31"
[[ -f "${dir}/$(name_at $(( start + 39 * 86400 )))" ]] || fail "newest dump pruned"
[[ -f "${dir}/$(name_at $(( start + 9 * 86400 )))" ]] || fail "30-day-old dump pruned"

# 7c. The newest scheduled dump is never pruned, however old (prune keeps the last one).
rm -f "${dir}"/owl_db-*
old1="$(name_at $(( now7 - 90 * 86400 )))"; old2="$(name_at $(( now7 - 60 * 86400 )))"
printf 'PGDMP\n' > "${dir}/${old1}"; printf 'PGDMP\n' > "${dir}/${old2}"
env BACKUP_DIR="${dir}" NOW_EPOCH="${now7}" bash -c 'source <(sed -n "/^prune() {/,/^}/p; /^now() {/p; /^log() {/p; /^scheduled_dumps() {/,/^}/p; /^dump_epoch() {/,/^}/p" "$1"); BACKUP_KEEP_DAYS=30; prune' _ "${script}" >> "${test_root}/log" 2>&1
[[ -f "${dir}/${old2}" ]] || fail "newest dump pruned although it was the only recent copy"
[[ ! -f "${dir}/${old1}" ]] || fail "90-day-old dump kept"

# 7d. A dump is written mode 600 (it holds every case), whatever umask the caller has.
rm -f "${dir}"/owl_db-*
( umask 022; run "${now7}" dump ) || fail "dump for mode check failed"
[[ "$(stat -c %a "${dir}/$(name_at "${now7}")")" == "600" ]] || fail "dump mode $(stat -c %a "${dir}/$(name_at "${now7}")"), expected 600"

# 8. Hand-made dumps in the same directory are never pruned.
touch "${dir}/owl_db-20261023-1649-pre-pid-d5.dump"
run $(( now7 + 86400 )) dump || fail "dump 40 failed"
[[ -f "${dir}/owl_db-20261023-1649-pre-pid-d5.dump" ]] || fail "hand-made dump pruned"

# 9. Sealed dumps. With a key whose custody is not proven the plain dump stays; a proven key removes it, the check reads
# the sealed file, retention takes the sealed files too, and what was plain before custody is sealed by the next run.
crypt="${source_dir}/backup-crypt.sh"
rm -f "${dir}"/owl_db-* "${dir}"/.owl_db-*
bash "${crypt}" new-key < /dev/null | sed -n '/BEGIN PGP PRIVATE/,/END PGP PRIVATE/p' > "${test_root}/private.asc"
t9="$(epoch '2027-01-20 01:30')"
old_plain="$(name_at $(( t9 - 86400 )))"
run $(( t9 - 86400 )) dump || fail "dump with an unproven key failed"
[[ -s "${dir}/${old_plain}" && -s "${dir}/${old_plain}.gpg" ]] || fail "unproven custody: plain and sealed not both kept"
[[ "$(bash "${crypt}" open "${dir}/${old_plain}.gpg" "${test_root}/private.asc" | sha256sum)" == "$(sha256sum < "${dir}/${old_plain}")" ]] || fail "sealed dump does not open to the dump"
bash "${crypt}" confirm-key < "${test_root}/private.asc" > /dev/null
: > "${alerts}"
run "${t9}" dump || fail "sealed dump failed"
new="$(name_at "${t9}")"
[[ ! -e "${dir}/${new}" && -s "${dir}/${new}.gpg" ]] || fail "plain dump left after custody"
[[ ! -e "${dir}/${old_plain}" && -s "${dir}/${old_plain}.gpg" ]] || fail "older plain dump not sealed by the next run"
[[ "$(stat -c %a "${dir}/${new}.gpg")" == 600 ]] || fail "sealed dump not mode 600"
run "${t9}" check || fail "check failed on a sealed dump: $(cat "${alerts}")"
later="$(name_at $(( t9 + 86400 )))"
run $(( t9 + 86400 )) dump || fail "dump after a sealed dump failed (size rule cannot read a sealed previous dump?)"
rm -f "${SEAL_DIR}/recovery-public.asc"
: > "${alerts}"
if run $(( t9 + 86400 )) check; then fail "check passed a sealed dump with the key gone"; fi
grep -q "sealed but not to this box's recovery key" "${alerts}" || fail "no alert for the wrong key"
: > "${alerts}"
run $(( t9 + 40 * 86400 )) dump || fail "dump for sealed retention failed"
[[ ! -e "${dir}/${later}.gpg" && ! -e "${dir}/${later}.gpg.sha256" && ! -e "${dir}/${new}.gpg" ]] || fail "retention left a sealed dump"

echo "test-db-backup: all passed"
