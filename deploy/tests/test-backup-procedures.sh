#!/usr/bin/env bash
# Expiry report, two-person deletion, and that the procedures name only commands that exist.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root:?}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export BACKUP_ROOT="${test_root}/backups" HAND_DUMPS="${test_root}/db-backups"
mkdir -p "${HAND_DUMPS}"; : > "${HAND_DUMPS}/old-by-hand.dump"
mkdir -p "${BACKUP_ROOT}"/{scheduled,neo4j/neo4j-20261020-0210Z,neo4j/neo4j-20261105-0210Z,chroma/chroma-20261103-0230Z,keys/keys-20261105-0205Z}
: > "${BACKUP_ROOT}/scheduled/owl_db-20261020-0130Z.dump"
: > "${BACKUP_ROOT}/scheduled/owl_db-20261020-0130Z.counts.tsv"
: > "${BACKUP_ROOT}/scheduled/owl_db-20261103-0130Z.dump.gpg"
: > "${BACKUP_ROOT}/scheduled/owl_db-20261105-0130Z.dump"
: > "${BACKUP_ROOT}/owl_db-20261023-1649-pre-pid-d5.dump"
fail() { echo "FAIL: $*"; exit 1; }
expiry() { bash "${source_dir}/backup-expiry.sh" "$@"; }
del() { bash "${source_dir}/two-person-delete.sh" "$@"; }

out="$(expiry report)"
grep -q '^postgres: 3 sets, oldest 20261020-0130, newest 20261105-0130, kept 30 days' <<<"${out}" || fail "report: ${out}"
grep -q '^chroma: 1 sets.*kept 14 days' <<<"${out}" || fail "chroma line: ${out}"
grep -q 'owl_db-20261023-1649-pre-pid-d5.dump' <<<"${out}" || fail "a dump with no expiry is not listed: ${out}"
grep -q 'old-by-hand.dump' <<<"${out}" || fail "the other dump folder is not listed: ${out}"
: > "${BACKUP_ROOT}/scheduled/.owl_db-20261104-0130Z.dump.suspect"
grep -q 'owl_db-20261104-0130Z.dump.suspect' <<<"$(expiry report)" || fail "a suspect dump is not listed"
out="$(expiry report --removed-on 2026-11-04)"
grep -q 'newest set that can hold it: 20261103-0130; out by 2026-12-04' <<<"${out}" || fail "postgres expiry: ${out}"
grep -q 'out of every set by: 2026-12-04' <<<"${out}" || fail "the last expiry across stores: ${out}"
if expiry report --removed-on yesterday 2>/dev/null; then fail "bad date accepted"; fi

# Two people: the asker cannot approve, in any spelling; nothing moves without approval.
id="$(del request neo4j-20261020-0210Z --by Neil@example.com --reason 'customer asked')"
if del execute "${id}" 2>/dev/null; then fail "ran with no approval"; fi
if del approve "${id}" --by ' neil@EXAMPLE.com' 2>/dev/null; then fail "the asker approved"; fi
[[ -d "${BACKUP_ROOT}/neo4j/neo4j-20261020-0210Z" ]] || fail "a refused request deleted"
del approve "${id}" --by second@example.com > /dev/null
del execute "${id}" > /dev/null
[[ ! -e "${BACKUP_ROOT}/neo4j/neo4j-20261020-0210Z" ]] || fail "approved set not deleted"
if del execute "${id}" 2>/dev/null; then fail "ran twice"; fi
for word in requested approved deleted; do grep -q "${id}	${word}" "${BACKUP_ROOT}/deletions/log.tsv" || fail "${word} not logged"; done

# A dump goes with its counts and meta; plain and sealed names both resolve.
id="$(del request owl_db-20261020-0130Z.dump --by a --reason r)"; del approve "${id}" --by b > /dev/null; del execute "${id}" > /dev/null
[[ ! -e "${BACKUP_ROOT}/scheduled/owl_db-20261020-0130Z.dump" && ! -e "${BACKUP_ROOT}/scheduled/owl_db-20261020-0130Z.counts.tsv" ]] || fail "dump or its counts left"
id="$(del request owl_db-20261103-0130Z.dump --by a --reason r)"; del approve "${id}" --by b > /dev/null; del execute "${id}" > /dev/null
[[ ! -e "${BACKUP_ROOT}/scheduled/owl_db-20261103-0130Z.dump.gpg" ]] || fail "sealed dump left"

# What the report lists as needing a person can be asked for.
id="$(del request .owl_db-20261104-0130Z.dump.suspect --by a --reason r)"; del approve "${id}" --by b > /dev/null; del execute "${id}" > /dev/null
[[ ! -e "${BACKUP_ROOT}/scheduled/.owl_db-20261104-0130Z.dump.suspect" ]] || fail "suspect dump left"
id="$(del request old-by-hand.dump --by a --reason r)"; del approve "${id}" --by b > /dev/null; del execute "${id}" > /dev/null
[[ ! -e "${HAND_DUMPS}/old-by-hand.dump" ]] || fail "dump in the other folder left"

# Never the newest of a store, never a path, never a stranger's file, and an old request lapses.
id="$(del request owl_db-20261105-0130Z.dump --by a --reason r)"; del approve "${id}" --by b > /dev/null
if del execute "${id}" 2>/dev/null; then fail "deleted the newest set"; fi
[[ -e "${BACKUP_ROOT}/scheduled/owl_db-20261105-0130Z.dump" ]] || fail "newest set gone"
for bad in ../etc/passwd status.tsv .lock nothing-20261105-0130Z; do
    if del request "${bad}" --by a --reason r 2>/dev/null; then fail "accepted ${bad}"; fi
done
id="$(NOW_EPOCH=$(( $(date +%s) - 8 * 86400 )) del request owl_db-20261023-1649-pre-pid-d5.dump --by a --reason r)"
if del approve "${id}" --by b 2>/dev/null; then fail "a lapsed request was approved"; fi

# A case is never deleted here: the second person does it in the app, and the book says so.
id="$(del request-case cded78d0-e659-44cc-940d-d8f8c8012760 --by a --reason r)"
del approve "${id}" --by b > /dev/null
del execute "${id}" | grep -q 'b now deletes case' || fail "case release not said"
grep -q "${id}	released	case" "${BACKUP_ROOT}/deletions/log.tsv" || fail "case release not logged"

# Each `bash deploy/<script> <word>` in the procedures is a script that exists and a word its usage knows.
doc="${source_dir}/../docs/customer-data-procedures.md"
[[ -f "${doc}" ]] || fail "no procedures document"
n=0
while read -r script word; do
    n=$(( n + 1 ))
    [[ -f "${source_dir}/${script}" ]] || fail "the procedures name deploy/${script}, which does not exist"
    case "${word}" in ''|\<*|--*|\$*) continue ;; esac
    grep -qE "(^|[ |\"(])${word}([ |)\"]|\$)" "${source_dir}/${script}" || fail "deploy/${script} has no ${word}"
done < <(grep -oE 'deploy/[a-z0-9_-]+\.(sh|py) +[a-z<$-][^ `]*|deploy/[a-z0-9_-]+\.(sh|py)' "${doc}" | sed 's#^deploy/##')
(( n >= 6 )) || fail "only ${n} commands found in the procedures"
echo "test-backup-procedures: all passed"
