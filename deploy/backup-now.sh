#!/usr/bin/env bash
# A full recovery set on demand, before a release: keys, Postgres, Neo4j and Chroma, through the same scripts the timers
# run, into the same directories, under the same retention and encryption.
#
#   backup-now.sh           refuse or take the set; writes <BACKUP_ROOT>/manual/set-YYYYMMDD-HHMMZ.txt; exit 0 only if all four wrote
#   backup-now.sh --check   say whether a set would run now, and write nothing
#
# It refuses at once, rather than waiting as a timer does: the person at the keyboard decides what to do next.
#   memory  the Neo4j step needs its scratch container plus the fleet's floor (MEM_FLOOR_MB + 2000 MB, as the timer)
#   disk    twice the newest dump and Chroma copy, the 8 GB the Neo4j step demands, and the same again for sealed files
#           while plain ones are kept beside them; the same rule the dump scripts apply one by one
# A store that fails does not stop the others, and that store's earlier sets stay.
set -uo pipefail
umask 077
LOG_NAME=backup-now
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${HERE}/backup-lib.sh"
. "${HERE}/backup-crypt.sh"
BACKUP_ROOT="${BACKUP_ROOT:-/mnt/owl-data/backups}"
PG_DIR="${PG_DIR:-${BACKUP_ROOT}/scheduled}"
NEO4J_DIR="${NEO4J_DIR:-${BACKUP_ROOT}/neo4j}"
CHROMA_DIR="${CHROMA_DIR:-${BACKUP_ROOT}/chroma}"
KEYS_DIR="${KEYS_DIR:-${BACKUP_ROOT}/keys}"
MANUAL_DIR="${MANUAL_DIR:-${BACKUP_ROOT}/manual}"

newest_dump() { find "${PG_DIR}" -maxdepth 1 -type f \( -name 'owl_db-[0-9]*Z.dump' -o -name 'owl_db-[0-9]*Z.dump.gpg' \) -printf '%f\n' 2>/dev/null | sed 's/\.gpg$//' | sort -u | tail -n 1; }
newest_set() { BACKUP_DIR="$1" sets "$2" | tail -n 1; }

disk_needed_mb() {
    local dump chroma pg_b=0 chroma_b=0 mb
    dump="$(newest_dump)"; chroma="$(newest_set "${CHROMA_DIR}" chroma)"
    [[ -n "${dump}" ]] && pg_b="$(stored_size "${PG_DIR}/${dump}")"
    if [[ -n "${chroma}" ]]; then
        chroma_b=$(( $(stored_size "${CHROMA_DIR}/${chroma}/chroma.sqlite3") + $(stored_size "${CHROMA_DIR}/${chroma}/hnsw.tar") ))
    fi
    mb=$(( (pg_b + chroma_b) * 2 / 1048576 + 8192 ))
    [[ "$(seal_state)" == unconfirmed ]] && mb=$(( mb * 2 ))
    echo "${mb}"
}

preflight() {  # prints the reason and returns 1 when a set must not start
    local need free_mb avail
    MEM_WAIT_S=0
    need=$(( MEM_FLOOR_MB + 2000 ))
    avail="$(awk '/^MemAvailable:/ {print int($2 / 1024)}' "${MEMINFO:-/proc/meminfo}")"
    if ! wait_for_memory 2000 >/dev/null; then
        echo "REFUSED: ${avail} MB of memory available, ${need} MB needed (the Neo4j step's scratch container and the fleet's floor)"
        return 1
    fi
    mkdir -p "${BACKUP_ROOT}"
    need="$(disk_needed_mb)"
    free_mb="$(df -Pm "${BACKUP_ROOT}" | awk 'NR==2 {print $4}')"
    if (( free_mb < need )); then
        echo "REFUSED: ${free_mb} MB free in ${BACKUP_ROOT}, ${need} MB needed"
        return 1
    fi
    echo "ok: ${avail} MB of memory, ${free_mb} MB of disk free (${need} MB needed); encryption: $(seal_state)"
}

unsealed() {  # <label> <newest name>: what should be sealed and is not. Sealing failing does not fail a dump script
    [[ "$(seal_state)" != none ]] || return 0
    local f
    case "$1" in
        postgres) [[ -s "${PG_DIR}/$2.gpg" ]] || echo "$2" ;;
        neo4j) for f in neo4j.dump system.dump; do [[ -s "${NEO4J_DIR}/$2/${f}.gpg" ]] || echo "${f}"; done ;;
        chroma) for f in hnsw.tar chroma.sqlite3; do [[ -s "${CHROMA_DIR}/$2/${f}.gpg" ]] || echo "${f}"; done ;;
    esac
}

step() {  # <label> <dir> <script> <prefix>: run one store's dump and record what it wrote
    local label="$1" dir="$2" script="$3" prefix="$4" before after t0 rc=0
    before="$(newest_set "${dir}" "${prefix}")"
    [[ "${prefix}" == owl_db ]] && before="$(newest_dump)"
    t0="$(date -u +%s)"
    BACKUP_DIR="${dir}" nice -n 15 bash "${HERE}/${script}" dump || rc=$?
    after="$(newest_set "${dir}" "${prefix}")"
    [[ "${prefix}" == owl_db ]] && after="$(newest_dump)"
    local open=""
    if (( rc == 0 )) && [[ -n "${after}" && "${after}" != "${before}" ]]; then
        open="$(unsealed "${label}" "${after}" | tr '\n' ' ')"
    fi
    if [[ -n "${open}" ]]; then
        printf '%s\tFAILED: %s, not sealed: %s\t%s s\n' "${label}" "${after}" "${open}" "$(( $(date -u +%s) - t0 ))" >> "${record}"
        failed=$(( failed + 1 ))
    elif (( rc == 0 )) && [[ -n "${after}" && "${after}" != "${before}" ]]; then
        printf '%s\t%s\t%s s\n' "${label}" "${after}" "$(( $(date -u +%s) - t0 ))" >> "${record}"
    else
        printf '%s\tFAILED (exit %s), newest is %s\t%s s\n' "${label}" "${rc}" "${after:-none}" "$(( $(date -u +%s) - t0 ))" >> "${record}"
        failed=$(( failed + 1 ))
    fi
}

verdict="$(preflight)"; rc=$?
echo "${verdict}"
(( rc == 0 )) || exit 1
[[ "${1:-}" != --check ]] || exit 0

mkdir -p "${MANUAL_DIR}"
exec 8>"${MANUAL_DIR}/.lock"
flock -n 8 || { echo "REFUSED: another manual backup is running"; exit 1; }
failed=0
record="${MANUAL_DIR}/.set-$(stamp)Z.partial"
started="$(date -u +%s)"
{ printf 'manual recovery set %s, app %s, encryption %s\n' "$(date -u +%FT%TZ)" "$(served_commit)" "$(seal_state)"; } > "${record}"
step keys "${KEYS_DIR}" keys-bundle.sh keys
step postgres "${PG_DIR}" db-backup.sh owl_db
step neo4j "${NEO4J_DIR}" neo4j-backup.sh neo4j
step chroma "${CHROMA_DIR}" chroma-backup.sh chroma
printf 'total %s s\n' "$(( $(date -u +%s) - started ))" >> "${record}"
if (( failed )); then echo "RESULT FAILED (${failed})" >> "${record}"; else echo "RESULT OK" >> "${record}"; fi
final="${MANUAL_DIR}/$(basename "${record}" .partial | sed 's/^\.//').txt"
mv -f -- "${record}" "${final}"
cat "${final}"
exit $(( failed > 0 ))
