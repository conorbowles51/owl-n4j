#!/usr/bin/env bash
# Daily copy of the vector store (the owl-v2_chromadb-data volume) off the boot disk, and the freshness check.
#
#   chroma-backup.sh dump    write <BACKUP_DIR>/chroma-YYYYMMDD-HHMMZ/{hnsw.tar,chroma.sqlite3,counts.tsv,meta.env}
#   chroma-backup.sh check   exit 1 (and run BACKUP_ALERT_CMD) unless the newest set is under 25 h old and whole
#
# Chroma keeps its records in chroma.sqlite3 and each vector index in a folder of files. The vectors cost a paid
# embedding call each to make again, so they are copied, not rebuilt. The index folders are read first and the
# database after, so the database is never behind an index: on start Chroma brings an index forward from the
# database's own queue. An index file that changes while it is read sends the run round again. The database is read
# through SQLite's backup call, which holds no lock between steps and restarts by itself if a write lands.
#
# Nothing is compressed: gzip -1 of the indexes managed 207 MB in 8 minutes at nice 15 and load 40 (5 Nov 2026) and
# vectors barely compress. A set is 1.44 GB, so the default 14 days (the vectors change far less often than the
# dumps) is about 20 GB. Way back to 30 days: Environment=BACKUP_KEEP_DAYS=30 in the unit.
#
# The copy is sealed by deploy/backup-crypt.sh when a recovery key is on the box.
#
# Install: see the header of deploy/owl-chroma-backup.service.
set -euo pipefail
umask 077
LOG_NAME=chroma-backup
BACKUP_DIR="${BACKUP_DIR:-/mnt/owl-data/backups/chroma}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
. "$(dirname "${BASH_SOURCE[0]}")/backup-lib.sh"
. "$(dirname "${BASH_SOURCE[0]}")/backup-crypt.sh"
CHROMA_DATA="${CHROMA_DATA:-/var/lib/docker/volumes/owl-v2_chromadb-data/_data}"
COPY_TRIES="${COPY_TRIES:-3}"
PY="${PY:-python3}"

index_state() { find "${CHROMA_DATA}" -mindepth 2 -type f -printf '%p %s %T@\n' | LC_ALL=C sort | sha256sum | cut -d' ' -f1; }

copy_sqlite() {  # <dest file> <counts file>
    "${PY}" -I - "${CHROMA_DATA}/chroma.sqlite3" "$1" "$2" <<'PY'
import sqlite3, sys
src, dst, counts = sys.argv[1:4]
source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
target = sqlite3.connect(dst)
target.execute("PRAGMA journal_mode=OFF")
target.execute("PRAGMA synchronous=OFF")
source.backup(target, pages=4096, sleep=0.02)
source.close()
rows = target.execute(
    "SELECT c.name, count(e.id) FROM collections c LEFT JOIN segments s ON s.collection = c.id "
    "LEFT JOIN embeddings e ON e.segment_id = s.id GROUP BY c.name ORDER BY c.name").fetchall()
with open(counts, "w") as out:
    for name, n in rows:
        out.write(f"{name}\t{n}\n")
PY
}

do_dump() {
    guard_exit
    mkdir -p "${BACKUP_DIR}"
    exec 8>"${BACKUP_DIR}/.lock"
    flock -n 8 || { alert "a Chroma backup is already running"; return 1; }
    local name previous prev_size=0 size started tries=0 ok=0 s0 s1 rc
    name="chroma-$(stamp)Z"
    previous="$(sets chroma | tail -n 1)"
    [[ -n "${previous}" ]] && prev_size="$(stored_size "${BACKUP_DIR}/${previous}/chroma.sqlite3")"
    if [[ ! -f "${CHROMA_DATA}/chroma.sqlite3" ]]; then
        alert "no Chroma backup: ${CHROMA_DATA}/chroma.sqlite3 not found; newest is ${previous:-none}"
        return 1
    fi
    started="$(date -u +%s)"
    rm -rf -- "${BACKUP_DIR}"/.chroma-*.partial
    local out="${BACKUP_DIR}/.${name}.partial"
    mkdir -p "${out}"
    while (( tries < COPY_TRIES )); do
        tries=$(( tries + 1 ))
        s0="$(index_state)"
        # tar exit 1 is "file changed as we read it": the root folder's time moves as SQLite journals come and go.
        # index_state below decides whether an index moved. 2 and above is a real failure.
        rc=0; tar -C "${CHROMA_DATA}" --exclude='./chroma.sqlite3*' -cf "${out}/hnsw.tar" . || rc=$?
        if (( rc > 1 )); then log "try ${tries}: tar failed (exit ${rc})"; continue; fi
        s1="$(index_state)"
        if [[ "${s0}" != "${s1}" ]]; then log "try ${tries}: an index changed during the copy; again"; continue; fi
        rm -f -- "${out}/chroma.sqlite3"
        if ! copy_sqlite "${out}/chroma.sqlite3" "${out}/counts.tsv"; then
            rm -rf -- "${out}"
            alert "no Chroma backup: the SQLite copy failed; newest is ${previous:-none}"
            return 1
        fi
        # An index saved after the tar, with its queue trimmed before the database copy, would leave vectors in neither.
        if [[ "$(index_state)" == "${s0}" ]]; then ok=1; break; fi
        log "try ${tries}: an index changed during the database copy; again"
    done
    if (( ! ok )); then
        rm -rf -- "${out}"
        alert "no Chroma backup: the indexes kept changing in ${COPY_TRIES} tries; newest is ${previous:-none}"
        return 1
    fi
    size="$(stat -c %s "${out}/chroma.sqlite3")"
    if (( prev_size > 0 && size * 2 < prev_size )); then
        mv -f -- "${out}" "${BACKUP_DIR}/.${name}.suspect"
        alert "new Chroma copy is ${size} bytes, under half of ${previous} (${prev_size}); kept as .${name}.suspect, not pruning"
        return 1
    fi
    write_meta "${out}/meta.env" "chroma_image=$("${DOCKER}" inspect owl-v2-chromadb --format '{{.Image}}' 2>/dev/null || echo unknown)" "copy_tries=${tries}"
    local index_size; index_size="$(stat -c %s "${out}/hnsw.tar")"
    seal_one "${out}/hnsw.tar"
    seal_one "${out}/chroma.sqlite3"
    mv -f -- "${out}" "${BACKUP_DIR}/${name}"
    log "wrote ${name} (${size} bytes database, ${index_size} bytes indexes, $(( $(date -u +%s) - started )) s)"
    seal_pending "${BACKUP_DIR}" 2 hnsw.tar chroma.sqlite3
    prune_sets chroma
}

do_check() {
    check_set_age chroma "Chroma" || return 1
    local f
    for f in hnsw.tar chroma.sqlite3 counts.tsv meta.env; do
        if [[ -s "${BACKUP_DIR}/${NEWEST_SET}/${f}" ]]; then continue; fi
        if ! seal_check "${BACKUP_DIR}/${NEWEST_SET}/${f}.gpg"; then
            alert "newest Chroma backup ${NEWEST_SET} has no ${f}"
            return 1
        fi
    done
    log "ok: newest ${NEWEST_SET}, ${NEWEST_AGE_H} h old"
}

case "${1:-}" in
    dump) do_dump ;;
    check) do_check ;;
    *) echo "usage: $0 dump|check" >&2; exit 2 ;;
esac
