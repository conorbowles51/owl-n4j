#!/usr/bin/env bash
# Vector store copy: a temp volume with a small real SQLite file and index folder.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root:?}"' EXIT
export SEAL_DIR="${test_root}/seal"   # never the box's real keys
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
script="${source_dir}/chroma-backup.sh"
dir="${test_root}/backups"; vol="${test_root}/vol"; alerts="${test_root}/alerts"
mkdir -p "${vol}/segment-1"; echo vectors > "${vol}/segment-1/data_level0.bin"
python3 -I - "${vol}/chroma.sqlite3" <<'PY'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
db.executescript("""
create table collections (id text, name text); create table segments (id text, collection text);
create table embeddings (id integer primary key, segment_id text);
insert into collections values ('c1', 'chunks'), ('c2', 'entities');
insert into segments values ('s1', 'c1'), ('s2', 'c2');
insert into embeddings (segment_id) values ('s1'), ('s1'), ('s2');
""")
db.close()
PY
cat > "${test_root}/docker" <<'EOF'
#!/usr/bin/env bash
echo sha256:img
EOF
chmod +x "${test_root}/docker"
alert_cmd="${test_root}/alert"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$1" >> %q\n' "${alerts}" > "${alert_cmd}"; chmod +x "${alert_cmd}"
run() { env BACKUP_DIR="${dir}" DOCKER="${test_root}/docker" BACKUP_ALERT_CMD="${alert_cmd}" CHROMA_DATA="${vol}" LIVE_CHECKOUT="${test_root}" \
        NOW_EPOCH="$1" bash "${script}" "$2" >> "${test_root}/log" 2>&1; }
fail() { echo "FAIL: $*"; echo "--- log"; cat "${test_root}/log"; exit 1; }
epoch() { date -u -d "$1" +%s; }

: > "${alerts}"
if run "$(epoch '2026-11-05 03:00')" check; then fail "check passed with no set"; fi
run "$(epoch '2026-11-05 02:30')" dump || fail "good copy failed"
s="${dir}/chroma-20261105-0230Z"
printf 'chunks\t2\nentities\t1\n' | cmp - "${s}/counts.tsv" || fail "counts wrong"
tar -tf "${s}/hnsw.tar" | grep -q 'segment-1/data_level0.bin' || fail "index not in the tar"
tar -tf "${s}/hnsw.tar" | grep -q 'chroma.sqlite3' && fail "database in the tar"
python3 -I -c "import sqlite3,sys; assert sqlite3.connect(sys.argv[1]).execute('select count(*) from embeddings').fetchone()[0] == 3" "${s}/chroma.sqlite3" || fail "copied database wrong"
run "$(epoch '2026-11-05 12:00')" check || fail "fresh set failed"
: > "${alerts}"
if run "$(epoch '2026-11-06 03:31')" check; then fail "stale set passed"; fi
grep -q '25 h old' "${alerts}" || fail "no stale alert"

# An index that keeps changing while read gives no set and an alert.
cat > "${test_root}/tar" <<EOF
#!/usr/bin/env bash
date +%s%N >> "${vol}/segment-1/data_level0.bin"
exec /usr/bin/tar "\$@"
EOF
chmod +x "${test_root}/tar"; : > "${alerts}"
if PATH="${test_root}:${PATH}" run "$(epoch '2026-11-05 02:31')" dump; then fail "moving index accepted"; fi
[[ ! -d "${dir}/chroma-20261105-0231Z" ]] || fail "moving index became a set"
grep -q 'kept changing' "${alerts}" || fail "no alert for a moving index"

# An index saved during the database copy sends the run round again; an empty collection is still listed.
python3 -I - "${vol}/chroma.sqlite3" <<'PY'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1]); db.execute("insert into collections values ('c3', 'empty')"); db.commit(); db.close()
PY
cat > "${test_root}/python-mover" <<EOF
#!/usr/bin/env bash
c="${test_root}/py.n"; n="\$(cat "\$c" 2>/dev/null || echo 0)"; echo \$(( n + 1 )) > "\$c"
python3 "\$@"; rc=\$?
[[ "\$n" == 0 ]] && echo more >> "${vol}/segment-1/data_level0.bin"
exit \$rc
EOF
chmod +x "${test_root}/python-mover"
PY="${test_root}/python-mover" run "$(epoch '2026-11-05 02:40')" dump || fail "second try after a database-copy change failed"
grep -q 'during the database copy' "${test_root}/log" || fail "change during the database copy not noticed"
grep -q 'copy_tries=2' "${dir}/chroma-20261105-0240Z/meta.env" || fail "second try not recorded"
grep -q 'empty.0' "${dir}/chroma-20261105-0240Z/counts.tsv" || fail "empty collection not listed"

# Default retention is 14 days.
now2="$(epoch '2026-12-10 02:30')"
old="chroma-$(date -u -d "@$(( now2 - 15 * 86400 ))" +%Y%m%d-%H%M)Z"; keep="chroma-$(date -u -d "@$(( now2 - 13 * 86400 ))" +%Y%m%d-%H%M)Z"
mkdir "${dir}/${old}" "${dir}/${keep}"; echo x > "${dir}/${keep}/chroma.sqlite3"
run "${now2}" dump || fail "copy for retention failed"
[[ ! -d "${dir}/${old}" ]] || fail "15-day-old set kept"
[[ -d "${dir}/${keep}" ]] || fail "13-day-old set pruned"
# Sealed: only once custody is proven is the plain copy gone; the check and the size rule read the sealed files.
crypt="${source_dir}/backup-crypt.sh"
bash "${crypt}" new-key < /dev/null | sed -n '/BEGIN PGP PRIVATE/,/END PGP PRIVATE/p' > "${test_root}/private.asc"
s1="chroma-$(date -u -d "@$(( now2 + 3600 ))" +%Y%m%d-%H%M)Z"
run $(( now2 + 3600 )) dump || fail "copy with an unproven key failed"
[[ -s "${dir}/${s1}/hnsw.tar" && -s "${dir}/${s1}/hnsw.tar.gpg" && -s "${dir}/${s1}/chroma.sqlite3.gpg" ]] || fail "unproven custody: plain and sealed not both kept"
bash "${crypt}" confirm-key < "${test_root}/private.asc" > /dev/null
s2="chroma-$(date -u -d "@$(( now2 + 7200 ))" +%Y%m%d-%H%M)Z"
run $(( now2 + 7200 )) dump || fail "sealed copy failed"
[[ ! -e "${dir}/${s2}/hnsw.tar" && ! -e "${dir}/${s2}/chroma.sqlite3" && -s "${dir}/${s2}/hnsw.tar.gpg" ]] || fail "plain copy left after custody"
[[ ! -e "${dir}/${s1}/hnsw.tar" && -s "${dir}/${s1}/hnsw.tar.gpg" ]] || fail "earlier plain copy not removed by the next run"
run $(( now2 + 7200 )) check || fail "check failed on a sealed set"
run $(( now2 + 10800 )) dump || fail "copy after a sealed set failed"
bash "${crypt}" open "${dir}/${s2}/hnsw.tar.gpg" "${test_root}/private.asc" | tar -tf - > /dev/null || fail "sealed indexes do not open to a tar"
echo "test-chroma-backup: all passed"
