# Sourced by the backup scripts (neo4j-backup.sh, chroma-backup.sh, keys-bundle.sh, backup-check.sh, restore-drill.sh).
# A "set" is one directory <prefix>-YYYYMMDD-HHMMZ under BACKUP_DIR, written as .<name>.partial and renamed when it is
# whole, so a cut-off run never looks like a backup and never triggers pruning.
BACKUP_ALERT_CMD="${BACKUP_ALERT_CMD:-}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-25}"
DOCKER="${DOCKER:-docker}"
LIVE_CHECKOUT="${LIVE_CHECKOUT:-/home/conorbowles51/app-v3/owl-n4j}"
NOW_EPOCH="${NOW_EPOCH:-}"   # tests only: pretend "now" is this epoch second
MEM_FLOOR_MB="${MEM_FLOOR_MB:-3000}"   # the fleet's floor (fleet-gate.conf MIN_MEM_AVAIL_MB)
MEM_WAIT_S="${MEM_WAIT_S:-1800}"

now() { if [[ -n "${NOW_EPOCH}" ]]; then echo "${NOW_EPOCH}"; else date -u +%s; fi; }
stamp() { date -u -d "@$(now)" +%Y%m%d-%H%M; }
log() { printf '%s %s: %s\n' "$(date -u +%FT%TZ)" "${LOG_NAME:-backup}" "$*"; }

alert() {
    log "ALERT: $1"
    if [[ -n "${BACKUP_ALERT_CMD}" ]]; then
        # The reason is passed as one argument, never through a shell.
        ${BACKUP_ALERT_CMD} "$1" || log "alert command failed"
    fi
}

sets() {  # <prefix>: whole sets, oldest first (the name sorts by time)
    find "${BACKUP_DIR}" -maxdepth 1 -type d \
        -name "$1-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]Z" -printf '%f\n' 2>/dev/null | sort || true
}

set_epoch() {  # <prefix>-YYYYMMDD-HHMMZ -> epoch seconds
    local s="${1##*-}" d="${1%-*}"; d="${d##*-}"
    date -u -d "${d} ${s:0:2}:${s:2:2}" +%s
}

prune_sets() {  # <prefix>: drop sets older than BACKUP_KEEP_DAYS; the newest is never pruned, however old
    local -a all; mapfile -t all < <(sets "$1")
    local n="${#all[@]}" i cutoff
    (( n > 1 )) || return 0
    cutoff=$(( $(now) - BACKUP_KEEP_DAYS * 86400 ))
    for (( i = 0; i < n - 1; i++ )); do
        if (( $(set_epoch "${all[i]}") < cutoff )); then
            log "prune ${all[i]} (older than ${BACKUP_KEEP_DAYS} days)"
            rm -rf -- "${BACKUP_DIR:?}/${all[i]}"
        fi
    done
}

check_set_age() {  # <prefix> <store label>: alert and fail unless the newest set is under BACKUP_MAX_AGE_HOURS old
    local newest age_h
    newest="$(sets "$1" | tail -n 1)"
    if [[ -z "${newest}" ]]; then
        alert "no $2 backup in ${BACKUP_DIR}"
        return 1
    fi
    age_h=$(( ( $(now) - $(set_epoch "${newest}") ) / 3600 ))
    if (( age_h >= BACKUP_MAX_AGE_HOURS )); then
        alert "newest $2 backup ${newest} is ${age_h} h old (limit ${BACKUP_MAX_AGE_HOURS} h)"
        return 1
    fi
    NEWEST_SET="${newest}"
    NEWEST_AGE_H="${age_h}"
}

wait_for_memory() {  # <MB the scratch work needs>: 0 once MemAvailable clears it plus the fleet's floor
    local need=$(( $1 + MEM_FLOOR_MB )) waited=0 avail
    while :; do
        avail="$(awk '/^MemAvailable:/ {print int($2 / 1024)}' "${MEMINFO:-/proc/meminfo}")"
        (( avail >= need )) && return 0
        (( waited >= MEM_WAIT_S )) && { log "memory: ${avail} MB available, ${need} MB needed"; return 1; }
        sleep 30; waited=$(( waited + 30 ))
    done
}

write_meta() {  # <file> [key=value ...]: the recovery set's application version and image
    {
        printf 'taken_utc=%s\n' "$(date -u -d "@$(now)" +%FT%TZ)"
        printf 'app_commit=%s\n' "$(git -c safe.directory='*' -C "${LIVE_CHECKOUT}" rev-parse HEAD 2>/dev/null || echo unknown)"
        local kv; for kv in "${@:2}"; do printf '%s\n' "${kv}"; done
    } > "$1"
}
