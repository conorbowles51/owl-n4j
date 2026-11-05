#!/usr/bin/env bash
# The evidence copy: read-only on the source, verified, incremental, resumable, never overwrites a copy.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'chmod -R u+rw "${test_root:?}" 2>/dev/null; rm -rf -- "${test_root:?}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tool="${source_dir}/evidence_copy.py"
src="${test_root}/src"; dest="${test_root}/dest"; log="${test_root}/log"
mkdir -p "${src}/case/sub"
echo "statement one" > "${src}/case/a.pdf"; head -c 3000000 /dev/urandom > "${src}/case/sub/b.bin"; : > "${src}/case/empty"
ln -s /etc/hostname "${src}/case/link"; touch "${src}/.x.dump.partial"; touch -d '2020-02-03 04:05:06' "${src}/case/a.pdf"
fail() { echo "FAIL: $*"; echo "--- log"; cat "${log}"; exit 1; }
copy() { python3 -I "${tool}" run --dest "${dest}" --source "ev=${src}" "$@" >> "${log}" 2>&1; }
tally() { python3 -I -c "import json,sys; print(json.load(open(sys.argv[1]))['tally'][sys.argv[2]])" "${dest}/last-run.json" "$1"; }
# Every path's type, mode, size and times; access time on files too (reading a folder's list moves the folder's own).
state() { find "${src}" -printf '%p %y %m %s %T@ %C@ %l\n' | sort; find "${src}" -type f -printf '%p %A@\n' | sort; }

# An unmarked destination is refused and not created: a missing mount must not become a copy on the boot disk.
if copy; then fail "unmarked destination accepted"; fi
[[ ! -e "${dest}" ]] || fail "unmarked destination created"
python3 -I "${tool}" init --dest "${dest}" >> "${log}" 2>&1

before="$(state)"
copy || fail "first run failed"
[[ "$(state)" == "${before}" ]] || fail "the source changed: size, mode or a time"
[[ "$(tally copied)" -eq 3 ]] || fail "copied $(tally copied), expected 3"
cmp "${src}/case/sub/b.bin" "${dest}/files/ev/case/sub/b.bin" || fail "bytes differ"
[[ "$(stat -c %Y "${dest}/files/ev/case/a.pdf")" == "$(stat -c %Y "${src}/case/a.pdf")" ]] || fail "modification time not kept"
[[ ! -e "${dest}/files/ev/case/link" ]] || fail "symlink followed"
[[ ! -e "${dest}/files/ev/.x.dump.partial" ]] || fail "unfinished backup file copied"
( cd "${dest}" && sha256sum -c --quiet MANIFEST.sha256 ) >> "${log}" 2>&1 || fail "the manifest does not prove the copy"

# Second run: nothing read again.
copy || fail "second run failed"
[[ "$(tally skipped)" -eq 3 && "$(tally copied)" -eq 0 ]] || fail "second run was not incremental"

# A changed source: the earlier copy is kept, the new one replaces it.
old="$(sha256sum "${src}/case/a.pdf" | cut -c1-12)"; echo "statement two" > "${src}/case/a.pdf"
copy || fail "changed file failed"
[[ "$(tally changed)" -eq 1 ]] || fail "change not counted"
grep -q 'statement one' "${dest}/superseded/ev/case/a.pdf.${old}" || fail "earlier copy not kept"
grep -q 'statement two' "${dest}/files/ev/case/a.pdf" || fail "new copy missing"

# A deleted source stays in the copy.
rm "${src}/case/empty"; copy || fail "run after delete failed"
[[ "$(tally gone)" -eq 1 && -e "${dest}/files/ev/case/empty" ]] || fail "deleted file not kept and counted"

# Budget: stops early with exit 3, the rerun finishes the rest.
for i in 1 2 3 4 5 6 7 8; do echo "$i" > "${src}/case/n$i"; done
sed 's/time.monotonic() - started > args.budget_seconds/tally["copied"] >= 1/' "${tool}" > "${test_root}/stopper.py"
rc=0; python3 -I "${test_root}/stopper.py" run --dest "${dest}" --source "ev=${src}" --budget-seconds 1 >> "${log}" 2>&1 || rc=$?
[[ "${rc}" -eq 3 ]] || fail "budget stop gave exit ${rc}"
python3 -I -c "import json,sys; r=json.load(open(sys.argv[1])); assert r['stopped']=='budget' and not r['complete']" "${dest}/last-run.json" || fail "early stop not reported"
copy || fail "resume failed"
[[ -e "${dest}/files/ev/case/n8" ]] || fail "resume did not finish"

# The free-space floor stops the run, it never fills the disk.
echo new > "${src}/case/more"
rc=0; copy --min-free-gb 100000000 || rc=$?
[[ "${rc}" -eq 3 ]] || fail "space floor gave exit ${rc}"
python3 -I -c "import json,sys; assert json.load(open(sys.argv[1]))['stopped']=='space'" "${dest}/last-run.json" || fail "space stop not reported"
copy || fail "run after space stop failed"

# Damage to the copy is found by verify.
python3 -I "${tool}" verify --dest "${dest}" --sample 100 >> "${log}" 2>&1 || fail "verify failed on a good copy"
chmod u+w "${dest}/files/ev/case/sub/b.bin"; echo damage >> "${dest}/files/ev/case/sub/b.bin"
if python3 -I "${tool}" verify --dest "${dest}" --sample 100 >> "${log}" 2>&1; then fail "verify missed damage"; fi

# A destination inside a source is refused.
if python3 -I "${tool}" run --dest "${src}/copy" --source "ev=${src}" >> "${log}" 2>&1; then fail "destination inside the source accepted"; fi
[[ ! -e "${src}/copy" ]] || fail "refused run still wrote into the source"

# Every report keeps when the copy began and when a whole pass last finished; a stopped run does not reset them.
python3 -I -c "import json,sys; r=json.load(open(sys.argv[1])); assert r['first_started'] and r['last_complete']" "${dest}/last-run.json" || fail "pass times not reported"
echo "test-evidence-copy: all passed"
