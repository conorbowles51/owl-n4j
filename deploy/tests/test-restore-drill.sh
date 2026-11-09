#!/usr/bin/env bash
# The drill's evidence check, on a temp tree and a fake restored database. The container restores are proved by running
# the drill itself; this covers the verdicts.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root:?}"' EXIT
export SEAL_DIR="${test_root}/seal"   # never the box's real keys
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ev="${test_root}/ev"; mkdir -p "${ev}/folder" "${test_root}/work"
echo one > "${ev}/a"; echo two > "${ev}/b"
sha() { sha256sum "$1" | cut -d' ' -f1; }
cat > "${test_root}/docker" <<'EOF'
#!/usr/bin/env bash
cat "${FAKE_ROWS}"
EOF
chmod +x "${test_root}/docker"
rows="${test_root}/rows"; report="${test_root}/report"
fail() { echo "FAIL: $*"; cat "${report}"; exit 1; }
drill() {  # prints nothing; the verdicts go to the report
    : > "${report}"
    env FAKE_ROWS="${rows}" REPORT="${report}" DOCKER="${test_root}/docker" WORK="${test_root}/work" \
        EVIDENCE_KNOWN_MISSING="${KNOWN:-${test_root}/no-known-list}" bash -c '
        set -uo pipefail
        source <(sed -n "/^drill_evidence() {/,/^}/p" "$1")
        report="${REPORT}"; failures=0; SCRATCH_PG=x; PG_USER=u; PG_DB=d; SAMPLE=300; LIVE_CHECKOUT=/none
        EVIDENCE_COPY_DEST="${COPY:-}"
        note() { printf "%s\n" "$*" >> "${report}"; }
        pass() { note "PASS $*"; }
        fail() { note "FAIL $*"; failures=$(( failures + 1 )); }
        elapsed() { echo 0; }
        drill_evidence' _ "${source_dir}/restore-drill.sh"
}

# Files present and matching, and a folder row: all pass, and the folder is not hashed or called missing.
printf 'r1\t%s\t%s\nr2\t%s\t%s\nr3\t%s\txx\n' "${ev}/a" "$(sha "${ev}/a")" "${ev}/b" "$(sha "${ev}/b")" "${ev}/folder" > "${rows}"
drill
grep -q 'PASS evidence: all 3 rows name a file or folder that is on disk, 1 folders' "${report}" || fail "healthy rows not passed"
grep -q 'PASS evidence: 2 sampled' "${report}" || fail "sample not passed"
grep -q FAIL "${report}" && fail "healthy rows failed"

# A row whose file is gone fails the drill, whichever rows a sample would have picked.
printf 'r4\t%s\tzz\n' "${ev}/gone" >> "${rows}"
drill
grep -q 'no file on disk: row r4' "${report}" || fail "missing row not named"
grep -q 'FAIL evidence: 1 of 4 rows' "${report}" || fail "missing row did not fail"
grep -q 'FAIL evidence: 1 of 4 rows name a file that is not on disk: 0 known (listed in .*), 1 new' "${report}" ||
    fail "a missing row not on the known list was not counted new"

# Rows on the known list still fail the drill (no hiding), counted apart from new ones.
printf '# files to be supplied again\nr4\n' > "${test_root}/known.ids"
printf 'r5\t%s\tzz\n' "${ev}/gone-too" >> "${rows}"
KNOWN="${test_root}/known.ids" drill
grep -q "FAIL evidence: 2 of 5 rows name a file that is not on disk: 1 known (listed in ${test_root}/known.ids), 1 new" \
    "${report}" || fail "known and new missing rows not counted apart"
grep -q 'no file on disk: row r4 (known)' "${report}" || fail "known row not marked"
grep -q 'no file on disk: row r5$' "${report}" || fail "new row not named"

# Alerts: the same result is sent once, a changed one again, and a pass forgets it so a return is sent again.
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$1" >> "%s"\n' "${test_root}/sent" > "${test_root}/sender"
chmod +x "${test_root}/sender"
alerts() {  # <report>...: one drill check per report, through the drill's own functions; prints what was sent
    env SENDER="${test_root}/sender" DRILL="${source_dir}/restore-drill.sh" LIB="${source_dir}/backup-lib.sh" STATE="${test_root}/alert-state" \
        SENT="${test_root}/sent" bash -c '
        set -uo pipefail
        . "${LIB}"
        source <(sed -n "/^drill_failures() {/p; /^drill_signature() {/,/^}/p" "${DRILL}")
        ALERT_STATE_DIR="${STATE}"; BACKUP_ALERT_CMD="${SENDER}"
        for r in "$@"; do
            if grep -q "^RESULT PASS" "$r"; then alert_reset restore-drill
            else alert_once restore-drill "$(drill_signature "$r")" "did not pass: $(drill_failures "$r")"; fi
        done' _ "$@" > /dev/null
}
d1="${test_root}/d1"; d2="${test_root}/d2"; d3="${test_root}/d3"; ok="${test_root}/ok"
printf 'FAIL evidence: 16 of 49048 rows name a file that is not on disk: 16 known (listed in k), 0 new (13 s)\nRESULT FAIL (1)\n' > "${d1}"
printf 'FAIL evidence: 16 of 49100 rows name a file that is not on disk: 16 known (listed in k), 0 new (11 s)\nRESULT FAIL (1)\n' > "${d2}"
printf 'FAIL evidence: 17 of 49100 rows name a file that is not on disk: 16 known (listed in k), 1 new (12 s)\nRESULT FAIL (1)\n' > "${d3}"
printf 'RESULT PASS\n' > "${ok}"
: > "${test_root}/sent"
alerts "${d1}" "${d1}" "${d2}" "${d2}"
[[ "$(wc -l < "${test_root}/sent")" -eq 1 ]] || { cat "${test_root}/sent"; fail "the same result was sent more than once"; }
# The board (backup-check.sh) reads the reason from the first ALERT: line, sent or not.
out="$(env LIB="${source_dir}/backup-lib.sh" STATE="${test_root}/alert-state" SENDER="${test_root}/sender" bash -c '
    . "${LIB}"; ALERT_STATE_DIR="${STATE}"; BACKUP_ALERT_CMD="${SENDER}"
    alert_once restore-drill "$(cat "${STATE}/restore-drill")" "did not pass: same"')"
grep -m1 'ALERT:' <<< "${out}" | grep -q 'ALERT: did not pass: same (same result' || fail "a repeat has no ALERT: line for the board"
alerts "${d3}"
[[ "$(wc -l < "${test_root}/sent")" -eq 2 ]] || fail "a new missing file was not sent"
grep -q '1 new' "${test_root}/sent" || fail "the alert does not say what failed"
alerts "${ok}" "${d1}"
[[ "$(wc -l < "${test_root}/sent")" -eq 3 ]] || fail "a failure returning after a pass was not sent"

# A file whose bytes changed fails on the hash.
printf 'r1\t%s\t%s\n' "${ev}/a" "0000" > "${rows}"
drill
grep -q 'hash differs: row r1' "${report}" || fail "changed file not found"
grep -q 'FAIL evidence: 1 hash differences' "${report}" || fail "changed file did not fail"
# A sealed set: opened with the key, which proves the decrypt; refused and failed with no key, never skipped; a changed
# byte fails on the hash; plain is read only where there is no key.
crypt="${source_dir}/backup-crypt.sh"
store="${test_root}/store"; mkdir -p "${store}"
echo 'dump bytes' > "${store}/x.dump"
bash "${crypt}" new-key < /dev/null | sed -n '/BEGIN PGP PRIVATE/,/END PGP PRIVATE/p' > "${test_root}/private.asc"
bash "${crypt}" seal-file "${store}/x.dump"
reads() {  # <key file>: the verdict and the bytes for one file, through the drill's own functions
    : > "${report}"
    env REPORT="${report}" KEY="$1" STORE="${store}" DRILL="${source_dir}/restore-drill.sh" CRYPT="${crypt}" bash -c '
        set -uo pipefail
        . "${CRYPT}"
        source <(sed -n "/^how_to_read() {/,/^}/p; /^to_stdout() {/p" "${DRILL}")
        report="${REPORT}"; failures=0; BACKUP_PRIVATE_KEY_FILE="${KEY}"
        fail() { printf "FAIL %s
" "$*" >> "${report}"; }
        how_to_read "${STORE}/x.dump"
        echo "${HOW}"
        if [[ "${HOW}" == sealed ]]; then open_begin "${KEY}"; fi
        if [[ "${HOW}" != locked ]]; then to_stdout "${STORE}/x.dump" "${HOW}"; fi
        open_end'
}
[[ "$(reads "${test_root}/private.asc")" == $'sealed\ndump bytes' ]] || fail "sealed file not opened with the key"
[[ "$(reads /no/key)" == $'plain\ndump bytes' ]] || fail "plain not used with no key"
rm "${store}/x.dump"
[[ "$(reads /no/key)" == locked ]] || fail "sealed-only with no key was not locked"
grep -q 'FAIL x.dump: only sealed, and no private key here' "${report}" || fail "sealed-only with no key did not fail the drill"
printf 'x' | dd of="${store}/x.dump.gpg" bs=1 seek=100 conv=notrunc 2>/dev/null
[[ "$(reads "${test_root}/private.asc")" == locked ]] || fail "changed ciphertext was read"
grep -q 'does not match its hash' "${report}" || fail "changed ciphertext did not fail the drill"
# The reach verdict, from a scratch tool: every outcome reaches the report and an unreached record fails the drill.
reach_drill() {  # <exit code> <line printed>
    : > "${report}"
    mkdir -p "${test_root}/drills" "${test_root}/backend/scripts" "${test_root}/deploy"
    sed -n "/^drill_chroma_reach() {/,/^}/p" "${source_dir}/restore-drill.sh" > "${test_root}/fn"
    cat > "${test_root}/backend/scripts/chroma_reach.py" <<EOF
import sys
args = sys.argv
if "--out" in args: open(args[args.index("--out") + 1], "w").write("[]")
print("$2")
sys.exit($1)
EOF
    env REPORT="${report}" DRILLS="${test_root}/drills" ROOT="${test_root}" bash -c '
        set -uo pipefail
        source "${ROOT}/fn"
        report="${REPORT}"; failures=0; BACKUP_DIR="${DRILLS}"; HERE="${ROOT}/deploy"
        note() { printf "%s\n" "$*" >> "${report}"; }
        pass() { note "PASS $*"; }
        fail() { note "FAIL $*"; failures=$(( failures + 1 )); }
        elapsed() { echo 0; }
        stamp() { echo now; }
        drill_chroma_reach http://scratch'
}
reach_drill 0 "chunks: 10 of 10 found at depth 250, 0 searched records unreached"
grep -q 'PASS chroma: every stored record' "${report}" || fail "a clean reach did not pass"
[[ -z "$(ls -A "${test_root}/drills")" ]] || fail "a clean reach left a list behind"
reach_drill 1 "chunks: 9 of 10 found at depth 250, 1 searched records unreached (1 at any depth)"
grep -q 'FAIL chroma: stored records search cannot reach' "${report}" || fail "an unreached record did not fail"
[[ -s "${test_root}/drills/reach-now.json" ]] || fail "the list of unreached records was not kept"
rm -f "${test_root}/drills/"*
reach_drill 2 "Traceback"
grep -q 'FAIL chroma: the reach check did not finish' "${report}" || fail "a broken check did not fail"
echo "test-restore-drill: all passed"
