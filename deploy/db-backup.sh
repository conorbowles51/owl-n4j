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
# Retention: the newest BACKUP_KEEP_DAILY (7) dumps, plus the newest dump of each of the last BACKUP_KEEP_WEEKLY (4)
# ISO weeks. Measured 2026-11-03: owl_db is 4.4 GB on disk and dumped to 1.22 GB in 253 s (20:32 UTC, load 29-31), so 11 dumps are about 13.5 GB of
# the 357 GB free on /mnt/owl-data.
#
# Install: deploy/owl-db-backup.service + .timer, deploy/owl-db-backup-check.service + .timer (see their headers).
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/mnt/owl-data/backups/scheduled}"
PG_CONTAINER="${PG_CONTAINER:-owl-v2-pg}"
PG_USER="${PG_USER:-owl_us}"
PG_DB="${PG_DB:-owl_db}"
BACKUP_KEEP_DAILY="${BACKUP_KEEP_DAILY:-7}"
BACKUP_KEEP_WEEKLY="${BACKUP_KEEP_WEEKLY:-4}"
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
    local -a all keep=()
    mapfile -t all < <(scheduled_dumps)
    local n="${#all[@]}" i f week
    declare -A seen_week=()
    # Newest first: keep the daily window, then the newest dump of each recent ISO week.
    for (( i = n - 1; i >= 0; i-- )); do
        f="${all[i]}"
        week="$(date -u -d "@$(dump_epoch "$f")" +%G-%V)"
        if (( n - 1 - i < BACKUP_KEEP_DAILY )); then
            keep+=("$f"); seen_week["$week"]=1
        elif [[ -z "${seen_week[$week]:-}" && "${#seen_week[@]}" -lt $(( BACKUP_KEEP_WEEKLY + 1 )) ]]; then
            keep+=("$f"); seen_week["$week"]=1
        fi
    done
    for f in "${all[@]}"; do
        if [[ " ${keep[*]} " != *" $f "* ]]; then
            log "prune ${f}"
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
