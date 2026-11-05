#!/usr/bin/env bash
# The drill's evidence check, on a temp tree and a fake restored database. The container restores are proved by running
# the drill itself; this covers the verdicts.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root:?}"' EXIT
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
    env FAKE_ROWS="${rows}" REPORT="${report}" DOCKER="${test_root}/docker" WORK="${test_root}/work" bash -c '
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

# A file whose bytes changed fails on the hash.
printf 'r1\t%s\t%s\n' "${ev}/a" "0000" > "${rows}"
drill
grep -q 'hash differs: row r1' "${report}" || fail "changed file not found"
grep -q 'FAIL evidence: 1 hash differences' "${report}" || fail "changed file did not fail"
echo "test-restore-drill: all passed"
