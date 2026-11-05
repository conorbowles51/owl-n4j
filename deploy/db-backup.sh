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
# Beside each dump, owl_db-...Z.counts.tsv holds the rows per table and case read in the same database snapshot the
# dump reads (pg_dump --snapshot), and owl_db-...Z.meta the application commit. deploy/restore-drill.sh checks a
# restored dump against that file exactly; live has moved on by then. A run where the snapshot session fails still
# writes the dump, with no counts file, and alerts.
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
LIVE_CHECKOUT="${LIVE_CHECKOUT:-/home/conorbowles51/app-v3/owl-n4j}"
COUNTS_SQL="$(dirname "${BASH_SOURCE[0]}")/pg-counts.sql"

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
            rm -f -- "${BACKUP_DIR}/${f}" "${BACKUP_DIR}/${f%.dump}.counts.tsv" "${BACKUP_DIR}/${f%.dump}.meta"
        fi
    done
}

open_snapshot() {  # a read-only session whose snapshot pg_dump reads; SNAPSHOT is empty when that fails
    SNAPSHOT=""
    trap '' PIPE   # a session that dies must fail the write below, not end this script
    coproc PG_SESSION { "${DOCKER}" exec -i "${PG_CONTAINER}" nice -n 15 psql -U "${PG_USER}" -d "${PG_DB}" -AtqX -F $'\t' 2>/dev/null; }
    SESSION_IN="${PG_SESSION[1]:-}"; SESSION_OUT="${PG_SESSION[0]:-}"; SESSION_PID="${PG_SESSION_PID:-}"
    [[ -n "${SESSION_IN}" && -n "${SESSION_OUT}" ]] || return 0
    printf 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\nSELECT pg_export_snapshot();\n' >&"${SESSION_IN}" 2>/dev/null || return 0
    read -r -t 60 SNAPSHOT <&"${SESSION_OUT}" || SNAPSHOT=""
}

read_counts() {  # <file>: the counts in the dump's snapshot; 0 only when the whole list arrived
    local line got=1
    { cat "${COUNTS_SQL}"; printf "SELECT '__end__';\n"; } >&"${SESSION_IN}" 2>/dev/null || return 1
    while IFS= read -r -t 1800 line <&"${SESSION_OUT}"; do
        if [[ "${line}" == "__end__" ]]; then got=0; break; fi
        printf '%s\n' "${line}"
    done > "$1.raw"
    (( got == 0 )) || { rm -f -- "$1.raw"; return 1; }
    LC_ALL=C sort "$1.raw" > "$1"
    rm -f -- "$1.raw"
}

close_snapshot() {
    if [[ -n "${SESSION_IN:-}" ]]; then
        printf 'ROLLBACK;\n\\q\n' >&"${SESSION_IN}" 2>/dev/null || true
        eval "exec ${SESSION_IN}>&- ${SESSION_OUT}<&-" 2>/dev/null || true
    fi
    [[ -n "${SESSION_PID:-}" ]] && wait "${SESSION_PID}" 2>/dev/null || true
    SESSION_IN=""; SESSION_OUT=""; SESSION_PID=""
    return 0
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
    open_snapshot
    [[ -n "${SNAPSHOT}" ]] || alert "no snapshot session for ${name}: the dump goes ahead with no counts file"
    if ! "${DOCKER}" exec "${PG_CONTAINER}" nice -n 15 pg_dump -U "${PG_USER}" -d "${PG_DB}" -Fc ${SNAPSHOT:+"--snapshot=${SNAPSHOT}"} > "${partial}"; then
        close_snapshot
        rm -f -- "${partial}"
        alert "pg_dump of ${PG_DB} failed; no new dump; newest is ${previous:-none}"
        return 1
    fi
    local counts="${BACKUP_DIR}/.${name%.dump}.counts.partial"
    if [[ -n "${SNAPSHOT}" ]]; then
        read_counts "${counts}" || rm -f -- "${counts}"
    fi
    close_snapshot
    size="$(stat -c %s "${partial}")"
    if ! verify_dump "${partial}"; then
        rm -f -- "${partial}"
        alert "new dump of ${PG_DB} did not read back with pg_restore --list; discarded; newest is ${previous:-none}"
        return 1
    fi
    if (( prev_size > 0 && size * 2 < prev_size )); then
        mv -f -- "${partial}" "${BACKUP_DIR}/.${name}.suspect"
        rm -f -- "${counts}"
        alert "new dump is ${size} bytes, under half of ${previous} (${prev_size}); kept as .${name}.suspect, not pruning"
        return 1
    fi
    mv -f -- "${partial}" "${BACKUP_DIR}/${name}"
    if [[ -f "${counts}" ]]; then
        mv -f -- "${counts}" "${BACKUP_DIR}/${name%.dump}.counts.tsv"
    else
        alert "dump ${name} has no counts file: the snapshot session failed; the drill cannot check it exactly"
    fi
    printf 'taken_utc=%s\napp_commit=%s\n' "$(date -u -d "@$(now)" +%FT%TZ)" \
        "$(git -c safe.directory='*' -C "${LIVE_CHECKOUT}" rev-parse HEAD 2>/dev/null || echo unknown)" > "${BACKUP_DIR}/${name%.dump}.meta"
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
