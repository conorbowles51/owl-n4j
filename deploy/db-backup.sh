#!/usr/bin/env bash
# Nightly dump of the live database (owl_db in the owl-v2-pg container) with retention, and the freshness check.
#
#   db-backup.sh dump    write <dir>/owl_db-YYYYMMDD-HHMMZ.dump, verify it, then prune old scheduled dumps
#   db-backup.sh check   exit 1 (and run BACKUP_ALERT_CMD with the reason) unless the newest scheduled dump is
#                        younger than BACKUP_MAX_AGE_HOURS (25) and its table of contents reads back
#
# Only files this script names (owl_db-YYYYMMDD-HHMMZ.dump) in BACKUP_DIR are ever pruned; hand-made dumps elsewhere
# in /mnt/owl-data/backups are never touched. A dump is written to a .partial file and renamed only after
# pg_restore --list reads it back and it is at least half the size of the previous one, so a cut-off dump never
# replaces a good one and never triggers pruning.
#
# Retention (Neil 2026-11-04: "run nightly and keep 30 days, deleting anything older than 30 days"): a scheduled
# dump whose name-date is more than BACKUP_KEEP_DAYS (30) days before now is pruned; the newest scheduled dump is
# never pruned, however old. Measured 2026-11-03: owl_db is 4.4 GB on disk and dumped to 1.22 GB in 253 s (20:32 UTC,
# load 29-31), so 30-31 dumps are about 38 GB of the 352 GB free on /mnt/owl-data. Dumps are written mode 600.
#
# Install: deploy/owl-db-backup.service + .timer, deploy/owl-db-backup-check.service + .timer (see their headers).
set -euo pipefail
umask 077   # a dump holds every case; only root reads it

BACKUP_DIR="${BACKUP_DIR:-/mnt/owl-data/backups/scheduled}"
PG_CONTAINER="${PG_CONTAINER:-owl-v2-pg}"
PG_USER="${PG_USER:-owl_us}"
PG_DB="${PG_DB:-owl_db}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-25}"
BACKUP_ALERT_CMD="${BACKUP_ALERT_CMD:-}"
DOCKER="${DOCKER:-docker}"
NOW_EPOCH="${NOW_EPOCH:-}"   # tests only: pretend "now" is this epoch second

now() { if [[ -n "${NOW_EPOCH}" ]]; then echo "${NOW_EPOCH}"; else date -u +%s; fi; }
log() { printf '%s db-backup: %s\n' "$(date -u +%FT%TZ)" "$*"; }

alert() {
    log "ALERT: $1"
    if [[ -n "${BACKUP_ALERT_CMD}" ]]; then
        # The reason is passed as one argument, never through a shell.
        ${BACKUP_ALERT_CMD} "$1" || log "alert command failed"
    fi
}

# Scheduled dumps, oldest first (the name sorts by time).
scheduled_dumps() {
    find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'owl_db-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]Z.dump' \
        -printf '%f\n' 2>/dev/null | sort || true
}

verify_dump() {  # <file> -> 0 when pg_restore reads its table of contents and it lists table data
    local entries
    entries="$("${DOCKER}" exec -i "${PG_CONTAINER}" pg_restore --list < "$1" 2>/dev/null | grep -c 'TABLE DATA' || true)"
    [[ "${entries}" =~ ^[0-9]+$ && "${entries}" -gt 0 ]]
}

dump_epoch() {  # owl_db-YYYYMMDD-HHMMZ.dump -> epoch seconds
    local stamp="${1#owl_db-}"; stamp="${stamp%Z.dump}"
    date -u -d "${stamp:0:8} ${stamp:9:2}:${stamp:11:2}" +%s
}

prune() {
    local -a all
    mapfile -t all < <(scheduled_dumps)
    local n="${#all[@]}" i f cutoff
    (( n > 1 )) || return 0
    cutoff=$(( $(now) - BACKUP_KEEP_DAYS * 86400 ))
    # Oldest first; the last (newest) dump is never pruned.
    for (( i = 0; i < n - 1; i++ )); do
        f="${all[i]}"
        if (( $(dump_epoch "$f") < cutoff )); then
            log "prune ${f} (older than ${BACKUP_KEEP_DAYS} days)"
            rm -f -- "${BACKUP_DIR}/${f}"
        fi
    done
}

do_dump() {
    mkdir -p "${BACKUP_DIR}"
    local name partial previous prev_size size free_kb
    name="owl_db-$(date -u -d "@$(now)" +%Y%m%d-%H%M)Z.dump"
    partial="${BACKUP_DIR}/.${name}.partial"
    previous="$(scheduled_dumps | tail -n 1)"
    prev_size=0
    [[ -n "${previous}" ]] && prev_size="$(stat -c %s "${BACKUP_DIR}/${previous}")"
    free_kb="$(df -Pk "${BACKUP_DIR}" | awk 'NR==2 {print $4}')"
    if (( prev_size > 0 && free_kb * 1024 < prev_size * 2 )); then
        alert "not enough room in ${BACKUP_DIR} for a dump (${free_kb} KB free, last dump ${prev_size} bytes); nothing written"
        return 1
    fi
    rm -f -- "${BACKUP_DIR}"/.owl_db-*.partial
    local started; started="$(date -u +%s)"
    log "dump ${PG_DB} from ${PG_CONTAINER} -> ${name}"
    # pg_dump runs inside the container at nice 15; it reads a consistent snapshot and takes no locks that block
    # the app's reads or writes (only DDL waits on it).
    if ! "${DOCKER}" exec "${PG_CONTAINER}" nice -n 15 pg_dump -U "${PG_USER}" -d "${PG_DB}" -Fc > "${partial}"; then
        rm -f -- "${partial}"
        alert "pg_dump of ${PG_DB} failed; no new dump; newest is ${previous:-none}"
        return 1
    fi
    size="$(stat -c %s "${partial}")"
    if ! verify_dump "${partial}"; then
        rm -f -- "${partial}"
        alert "new dump of ${PG_DB} did not read back with pg_restore --list; discarded; newest is ${previous:-none}"
        return 1
    fi
    if (( prev_size > 0 && size * 2 < prev_size )); then
        mv -f -- "${partial}" "${BACKUP_DIR}/.${name}.suspect"
        alert "new dump is ${size} bytes, under half of ${previous} (${prev_size}); kept as .${name}.suspect, not pruning"
        return 1
    fi
    mv -f -- "${partial}" "${BACKUP_DIR}/${name}"
    log "wrote ${name} (${size} bytes, $(( $(date -u +%s) - started )) s)"
    prune
}

do_check() {
    local newest age_h
    newest="$(scheduled_dumps | tail -n 1)"
    if [[ -z "${newest}" ]]; then
        alert "no scheduled database dump in ${BACKUP_DIR}"
        return 1
    fi
    age_h=$(( ( $(now) - $(dump_epoch "${newest}") ) / 3600 ))
    if (( age_h >= BACKUP_MAX_AGE_HOURS )); then
        alert "newest database dump ${newest} is ${age_h} h old (limit ${BACKUP_MAX_AGE_HOURS} h)"
        return 1
    fi
    if ! verify_dump "${BACKUP_DIR}/${newest}"; then
        alert "newest database dump ${newest} does not read back with pg_restore --list"
        return 1
    fi
    log "ok: newest ${newest}, ${age_h} h old"
}

case "${1:-}" in
    dump) do_dump ;;
    check) do_check ;;
    *) echo "usage: $0 dump|check" >&2; exit 2 ;;
esac
