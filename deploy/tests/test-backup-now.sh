#!/usr/bin/env bash
# The manual recovery set: fake store scripts beside a copy of the script. Refusals, the record, a failed store.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root:?}"' EXIT
export SEAL_DIR="${test_root}/seal"
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cp "${source_dir}/backup-now.sh" "${source_dir}/backup-lib.sh" "${source_dir}/backup-crypt.sh" "${test_root}/"
root="${test_root}/backups"; mkdir -p "${root}"/{scheduled,neo4j,chroma,keys}
for pair in keys-bundle:keys db-backup:owl_db neo4j-backup:neo4j chroma-backup:chroma; do
    s="${pair%%:*}"; p="${pair##*:}"
    cat > "${test_root}/${s}.sh" <<X
#!/usr/bin/env bash
echo "\$\$" >> "${test_root}/ran"; echo "${s}" >> "${test_root}/order"
[[ -f "${test_root}/break-${s}" ]] && exit 1
n="\$(date -u -d "@\$(( 1800000000 + \$(wc -l < "${test_root}/order") * 60 ))" +%Y%m%d-%H%M)Z"
if [[ "${p}" == owl_db ]]; then echo x > "\${BACKUP_DIR}/owl_db-\${n}.dump"; else mkdir "\${BACKUP_DIR}/${p}-\${n}"; fi
X
done
mem="${test_root}/meminfo"
now_mem() { printf 'MemAvailable: %s kB\n' "$1" > "${mem}"; }
go() { env BACKUP_ROOT="${root}" MEMINFO="${mem}" BACKUP_HEALTH_URL="file:///nowhere" bash "${test_root}/backup-now.sh" "$@"; }
fail() { echo "FAIL: $*"; exit 1; }
ran() { [[ -e "${test_root}/ran" ]]; }

# Too little memory: refused at once, nothing runs. 4,999 MB is one short of the floor plus the scratch container.
now_mem $(( 4999 * 1024 ))
if out="$(go 2>&1)"; then fail "ran with too little memory"; fi
grep -q 'REFUSED: 4999 MB of memory available, 5000 MB needed' <<<"${out}" || fail "memory refusal: ${out}"
ran && fail "a store ran after a refusal"

# Too little disk: a newest dump bigger than the disk (sparse).
now_mem $(( 8000 * 1024 ))
truncate -s 15T "${root}/scheduled/owl_db-20261101-0130Z.dump"
if out="$(go 2>&1)"; then fail "ran with too little disk"; fi
grep -q 'REFUSED: .* MB free' <<<"${out}" || fail "disk refusal: ${out}"
ran && fail "a store ran after a disk refusal"
rm -f "${root}/scheduled"/owl_db-*

# --check says yes and writes nothing.
go --check | grep -q '^ok: ' || fail "--check did not pass"
ran && fail "--check ran a store"
[[ ! -e "${root}/manual" ]] || fail "--check wrote a record"

# All four write: in order, a record, exit 0.
go > "${test_root}/out" || fail "a good set failed: $(cat "${test_root}/out")"
[[ "$(tr '\n' ' ' < "${test_root}/order")" == "keys-bundle db-backup neo4j-backup chroma-backup " ]] || fail "order: $(cat "${test_root}/order")"
rec="$(find "${root}/manual" -name 'set-*Z.txt')"
[[ -n "${rec}" && "$(stat -c %a "${rec}")" == 600 ]] || fail "no private record"
grep -q '^RESULT OK' "${rec}" || fail "record: $(cat "${rec}")"
for s in keys postgres neo4j chroma; do grep -q "^${s}	" "${rec}" || fail "${s} not in the record"; done
grep -q '^postgres	owl_db-' "${rec}" || fail "record does not name the dump"

# One store fails: the others still run, exit 1, and the record says which. A store that writes nothing new also fails.
rm -f "${root}/manual"/set-*
touch "${test_root}/break-neo4j-backup"
if go > "${test_root}/out"; then fail "exit 0 with a failed store"; fi
grep -q '^neo4j	FAILED (exit 1)' "${test_root}/out" || fail "failure not recorded: $(cat "${test_root}/out")"
grep -q 'RESULT FAILED (1)' "${test_root}/out" || fail "no failed result"
grep -q '^chroma	chroma-' "${test_root}/out" || fail "a later store did not run"
# With a recovery key, a dump that did not get sealed is a failed set, though the dump script said yes.
rm -f "${test_root}/break-neo4j-backup"
bash "${test_root}/backup-crypt.sh" new-key < /dev/null > /dev/null
if go > "${test_root}/out"; then fail "unsealed set reported as a success"; fi
grep -q '^postgres	FAILED: owl_db-.*not sealed' "${test_root}/out" || fail "unsealed dump not said: $(cat "${test_root}/out")"
grep -q '^neo4j	FAILED: .*not sealed: neo4j.dump system.dump' "${test_root}/out" || fail "unsealed set not said"
echo "test-backup-now: all passed"
