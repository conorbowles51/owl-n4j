#!/usr/bin/env bash
# Daily dump of the live graph (owl-v2-n4j) with no stop of the live database, and the freshness check.
#
#   neo4j-backup.sh dump    write <BACKUP_DIR>/neo4j-YYYYMMDD-HHMMZ/{neo4j.dump,system.dump,counts.tsv,meta.env}
#   neo4j-backup.sh check   exit 1 (and run BACKUP_ALERT_CMD) unless the newest set is under 25 h old and whole
#
# Community Neo4j only dumps a stopped database. Measured 5 Nov 2026 on a copy of the live store at load 35-41: stop
# 12 s, dump 54 s, system database 23 s, start 83 s, so a stop would cost nearly 3 minutes of graph outage every day.
# Instead this copies the running store's files, then its transaction logs, starts the copy in a throwaway container
# (normal crash recovery replays what the copied store lacks), stops that cleanly and dumps it. The method needs no
# checkpoint between the first file read and the last: a checkpoint in that window would make recovery start after
# changes the copied store files do not hold. So the checkpoint log is hashed before and after, and a run that sees it
# change starts again. Node and relationship counts per case read from live before and after the copy are the
# independent proof: when they agree with each other, the recovered copy has to match them or the set is refused.
# Measured: 80,748 nodes, 196,935 relationships matched on the first try, 5 transactions replayed.
#
# Install: see the header of deploy/owl-neo4j-backup.service.
set -euo pipefail
umask 077   # a dump holds every case; only root reads it
LOG_NAME=neo4j-backup
BACKUP_DIR="${BACKUP_DIR:-/mnt/owl-data/backups/neo4j}"
. "$(dirname "${BASH_SOURCE[0]}")/backup-lib.sh"
NEO4J_CONTAINER="${NEO4J_CONTAINER:-owl-v2-n4j}"
NEO4J_DATA="${NEO4J_DATA:-${LIVE_CHECKOUT}/neo4j/data}"
SCRATCH="${SCRATCH:-lxbf-neo4j-backup}"
SCRATCH_MEM_MB="${SCRATCH_MEM_MB:-2000}"
COPY_TRIES="${COPY_TRIES:-3}"
READY_TRIES="${READY_TRIES:-200}"   # 3 s apart
READY_SLEEP="${READY_SLEEP:-3}"
COUNTS_QUERY="MATCH (n) OPTIONAL MATCH (n)-[r]->() RETURN coalesce(toString(n.case_id), '(none)') AS c, count(DISTINCT n) AS nodes, count(r) AS rels;"

work=""
cleanup() {
    "${DOCKER}" rm -f "${SCRATCH}" >/dev/null 2>&1 || true
    [[ -n "${work}" ]] && rm -rf -- "${work}"
    return 0
}

plain_to_tsv() { tail -n +2 | tr -d '"' | sed 's/, /\t/g' | LC_ALL=C sort; }

counts_live() {
    # The password comes from the container's own environment and is never on a command line.
    printf '%s\n' "${COUNTS_QUERY}" | "${DOCKER}" exec -i "${NEO4J_CONTAINER}" sh -c \
        'NEO4J_USERNAME="${NEO4J_AUTH%%/*}" NEO4J_PASSWORD="${NEO4J_AUTH#*/}" exec nice -n 15 cypher-shell --format plain' | plain_to_tsv
}

counts_scratch() {
    printf '%s\n' "${COUNTS_QUERY}" | "${DOCKER}" exec -i "${SCRATCH}" nice -n 15 cypher-shell --format plain | plain_to_tsv
}

checkpoint_hash() { cat "${NEO4J_DATA}"/transactions/*/checkpoint.* | sha256sum | cut -d' ' -f1; }

copy_store() {  # <dest>: store files first, transaction logs after, so the logs cover everything the store lacks
    rm -rf -- "$1"
    mkdir -p "$1/databases" "$1/transactions"
    cp -a "${NEO4J_DATA}/databases/neo4j" "${NEO4J_DATA}/databases/system" "$1/databases/" &&
        cp -a "${NEO4J_DATA}/transactions/neo4j" "${NEO4J_DATA}/transactions/system" "$1/transactions/" &&
        cp -a "${NEO4J_DATA}/dbms" "${NEO4J_DATA}/server_id" "$1/"
}

admin() {  # <data dir> <out dir> <neo4j-admin args...>
    local data="$1" out="$2"; shift 2
    "${DOCKER}" run --rm --name "${SCRATCH}-admin" --hostname localhost --memory 2g --cpus 2 --cpu-shares 128 \
        --network none -v "${data}:/data" -v "${out}:/out" --entrypoint /usr/bin/nice "${image}" -n 15 neo4j-admin "$@"
}

do_dump() {
    guard_exit
    mkdir -p "${BACKUP_DIR}"
    exec 8>"${BACKUP_DIR}/.lock"
    flock -n 8 || { alert "a Neo4j backup is already running"; return 1; }
    local name previous prev_size=0 size free_kb started tries=0 stable=0 before after recovered
    name="neo4j-$(stamp)Z"
    previous="$(sets neo4j | tail -n 1)"
    [[ -n "${previous}" ]] && prev_size="$(stat -c %s "${BACKUP_DIR}/${previous}/neo4j.dump")"
    free_kb="$(df -Pk "${BACKUP_DIR}" | awk 'NR==2 {print $4}')"
    if (( free_kb < 8 * 1024 * 1024 )); then
        alert "not enough room in ${BACKUP_DIR} for a Neo4j backup (${free_kb} KB free, 8 GB needed); nothing written"
        return 1
    fi
    if ! wait_for_memory "${SCRATCH_MEM_MB}"; then
        alert "no Neo4j backup: not enough free memory for the scratch container in ${MEM_WAIT_S} s; newest is ${previous:-none}"
        return 1
    fi
    if ! image="$("${DOCKER}" inspect "${NEO4J_CONTAINER}" --format '{{.Image}}')"; then
        alert "no Neo4j backup: container ${NEO4J_CONTAINER} not found; newest is ${previous:-none}"
        return 1
    fi
    started="$(date -u +%s)"
    rm -rf -- "${BACKUP_DIR}"/.work-* "${BACKUP_DIR}"/.neo4j-*.partial
    work="${BACKUP_DIR}/.work-${name}"
    local data="${work}/data" out="${BACKUP_DIR}/.${name}.partial"
    mkdir -p "${work}" "${out}"
    local copied=0
    while (( tries < COPY_TRIES )); do
        tries=$(( tries + 1 ))
        copied=0   # only the copy this try made counts; an earlier one is gone
        local ck0 ck1
        before="$(counts_live)" || { alert "no Neo4j backup: live counts could not be read; newest is ${previous:-none}"; rm -rf -- "${out}"; return 1; }
        ck0="$(checkpoint_hash)"
        if ! copy_store "${data}"; then log "try ${tries}: copy failed"; continue; fi
        ck1="$(checkpoint_hash)"
        after="$(counts_live)" || after=""
        if [[ "${ck0}" != "${ck1}" ]]; then log "try ${tries}: checkpoint during the copy; again"; continue; fi
        copied=1
        if [[ "${before}" == "${after}" ]]; then stable=1; break; fi
        log "try ${tries}: writes during the copy"
    done
    if (( ! copied )); then
        rm -rf -- "${out}"
        alert "no Neo4j backup: no whole copy free of a checkpoint in ${COPY_TRIES} tries; newest is ${previous:-none}"
        return 1
    fi
    log "store copied in $(( $(date -u +%s) - started )) s, ${tries} tries, stable=${stable}"
    "${DOCKER}" rm -f "${SCRATCH}" >/dev/null 2>&1 || true
    if ! "${DOCKER}" run -d --name "${SCRATCH}" --hostname localhost --memory 2g --cpus 2 --cpu-shares 128 --network none \
        -e NEO4J_AUTH=none -e NEO4J_server_memory_heap_initial__size=256m -e NEO4J_server_memory_heap_max__size=768m \
        -e NEO4J_server_memory_pagecache_size=512m -e NEO4J_db_transaction_timeout=0 -v "${data}:/data" \
        --entrypoint /usr/bin/nice "${image}" -n 15 tini -g -- /startup/docker-entrypoint.sh neo4j >/dev/null; then
        rm -rf -- "${out}"
        alert "no Neo4j backup: scratch container did not start; newest is ${previous:-none}"
        return 1
    fi
    local i ready=0
    for (( i = 0; i < READY_TRIES; i++ )); do
        if echo 'RETURN 1;' | "${DOCKER}" exec -i "${SCRATCH}" cypher-shell --format plain >/dev/null 2>&1; then ready=1; break; fi
        [[ "$("${DOCKER}" inspect "${SCRATCH}" --format '{{.State.Running}}' 2>/dev/null)" == true ]] || break
        sleep "${READY_SLEEP}"
    done
    if (( ! ready )); then
        rm -rf -- "${out}"
        alert "no Neo4j backup: the copied store did not recover in the scratch container; newest is ${previous:-none}"
        return 1
    fi
    recovered="$(counts_scratch)" || recovered=""
    if [[ -z "${recovered}" ]] || { (( stable )) && [[ "${recovered}" != "${before}" ]]; }; then
        rm -rf -- "${out}"
        alert "no Neo4j backup: recovered copy does not match the live counts per case; newest is ${previous:-none}"
        return 1
    fi
    "${DOCKER}" stop -t 120 "${SCRATCH}" >/dev/null
    "${DOCKER}" rm -f "${SCRATCH}" >/dev/null 2>&1 || true
    local db
    for db in neo4j system; do
        if ! admin "${data}" "${out}" database dump "${db}" --to-path=/out --overwrite-destination=true >/dev/null 2>&1; then
            rm -rf -- "${out}"
            alert "neo4j-admin dump of ${db} failed; no new set; newest is ${previous:-none}"
            return 1
        fi
    done
    size="$(stat -c %s "${out}/neo4j.dump")"
    if (( prev_size > 0 && size * 2 < prev_size )); then
        mv -f -- "${out}" "${BACKUP_DIR}/.${name}.suspect"
        alert "new Neo4j dump is ${size} bytes, under half of ${previous} (${prev_size}); kept as .${name}.suspect, not pruning"
        return 1
    fi
    printf '%s\n' "${before}" > "${out}/counts.tsv"
    (( stable )) || printf '%s\n' "${recovered}" > "${out}/counts.tsv"
    write_meta "${out}/meta.env" "neo4j_image=${image}" "counts_source=$( (( stable )) && echo live || echo recovered-copy )" "copy_tries=${tries}"
    chown -R root:root "${out}"; chmod -R go-rwx "${out}"
    mv -f -- "${out}" "${BACKUP_DIR}/${name}"
    log "wrote ${name} (${size} bytes, $(( $(date -u +%s) - started )) s)"
    prune_sets neo4j
}

do_check() {
    check_set_age neo4j "Neo4j" || return 1
    local f
    for f in neo4j.dump system.dump counts.tsv meta.env; do
        if [[ ! -s "${BACKUP_DIR}/${NEWEST_SET}/${f}" ]]; then
            alert "newest Neo4j backup ${NEWEST_SET} has no ${f}"
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
