#!/usr/bin/env bash
# The restore drill: the newest backups really restore, and what comes back is what was backed up.
#
#   restore-drill.sh run     restore into scratch containers, compare, print and store PASS or FAIL (exit 0 / 1)
#   restore-drill.sh check   exit 1 (and run BACKUP_ALERT_CMD) unless the newest drill passed and is under 8 days old
#
# Postgres: the newest scheduled dump goes into a scratch postgres of the live image, then rows per table and case
#   must equal the counts file read in the dump's own snapshot, line for line.
# Neo4j: the newest dump is loaded into a scratch neo4j of the live image, started, and nodes and relationships per
#   case must equal the set's counts file; neo4j-admin's consistency check runs on the loaded store.
# Chroma: the newest copy starts in a scratch chroma of the live image; records per collection must equal the set's
#   counts file, a sample of stored vectors must find themselves through the restored index at least as often as
#   through the live one, and every record must find itself inside its case at the app's depth
#   (backend/scripts/chroma_reach.py). The list of any it misses is kept in the drill folder.
# Evidence: every file the RESTORED database names must be on disk, and a random sample is hashed at its live path (and
#   in the copy, when EVIDENCE_COPY_DEST is set) against the hash the restored database holds.
# Keys: the newest bundle opens with the passphrase and each file equals its line in files.tsv.
# Sealed sets (deploy/backup-crypt.sh): the ciphertext's hash is checked and the set opened with the drill key, or with
# the key named in BACKUP_PRIVATE_KEY_FILE, so a drill proves the decrypt. A set that is only sealed, with no key here,
# fails the drill: it is a restore that could not be proved. Plain is used only where nothing can be decrypted.
# Live is the reference when the backup was taken, not when the drill runs: the drift since then is printed beside
# each check and does not fail the drill.
#
# One scratch container at a time, each removed before the next, under MEM_FLOOR_MB of free memory; all scratch data
# sits on the data disk under WORK and is removed at the end. Install: see deploy/owl-restore-drill.service.
set -uo pipefail
umask 077
LOG_NAME=restore-drill
BACKUP_DIR="${DRILL_DIR:-/mnt/owl-data/backups/drills}"
. "$(dirname "${BASH_SOURCE[0]}")/backup-lib.sh"
. "$(dirname "${BASH_SOURCE[0]}")/backup-crypt.sh"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PG_BACKUPS="${PG_BACKUPS:-/mnt/owl-data/backups/scheduled}"
NEO4J_BACKUPS="${NEO4J_BACKUPS:-/mnt/owl-data/backups/neo4j}"
CHROMA_BACKUPS="${CHROMA_BACKUPS:-/mnt/owl-data/backups/chroma}"
KEYS_BACKUPS="${KEYS_BACKUPS:-/mnt/owl-data/backups/keys}"
BACKUP_PRIVATE_KEY_FILE="${BACKUP_PRIVATE_KEY_FILE:-${SEAL_DRILL_PRIVATE}}"
WORK="${WORK:-/mnt/owl-data/tmp/lxbf-drill}"
PG_CONTAINER="${PG_CONTAINER:-owl-v2-pg}"; PG_USER="${PG_USER:-owl_us}"; PG_DB="${PG_DB:-owl_db}"
NEO4J_CONTAINER="${NEO4J_CONTAINER:-owl-v2-n4j}"
CHROMA_CONTAINER="${CHROMA_CONTAINER:-owl-v2-chromadb}"
CHROMA_LIVE_URL="${CHROMA_LIVE_URL:-http://127.0.0.1:8101}"
SAMPLE="${SAMPLE:-300}"
CHROMA_SAMPLE="${CHROMA_SAMPLE:-25}"
EVIDENCE_COPY_DEST="${EVIDENCE_COPY_DEST:-}"
DRILL_MAX_AGE_DAYS="${DRILL_MAX_AGE_DAYS:-8}"
SCRATCH_PG=lxbf-drill-pg; SCRATCH_N4J=lxbf-drill-n4j; SCRATCH_CHROMA=lxbf-drill-chroma
LIMITS=(--memory 2g --cpus 2 --cpu-shares 128)
COUNTS_QUERY="MATCH (n) OPTIONAL MATCH (n)-[r]->() RETURN coalesce(toString(n.case_id), '(none)') AS c, count(DISTINCT n) AS nodes, count(r) AS rels;"
API=api/v2/tenants/default_tenant/databases/default_database

failures=0
report=""
note() { printf '%s\n' "$*" | tee -a "${report}"; }
pass() { note "PASS $*"; }
fail() { note "FAIL $*"; failures=$(( failures + 1 )); }
elapsed() { echo $(( $(date -u +%s) - $1 )); }

cleanup() {
    open_end
    "${DOCKER}" rm -f "${SCRATCH_PG}" "${SCRATCH_N4J}" "${SCRATCH_N4J}-admin" "${SCRATCH_CHROMA}" >/dev/null 2>&1 || true
    rm -rf -- "${WORK}"
    return 0
}

# how_to_read <plain path>: sets HOW to sealed (open it, so proving the decrypt), plain, or locked (already failed)
how_to_read() {
    HOW=locked
    if [[ -f "$1.gpg" && -f "${BACKUP_PRIVATE_KEY_FILE}" ]]; then
        if seal_hash_ok "$1.gpg"; then HOW=sealed; else fail "$(basename "$1").gpg: the file does not match its hash"; fi
    elif [[ -f "$1" ]]; then
        HOW=plain
    elif [[ -f "$1.gpg" ]]; then
        fail "$(basename "$1"): only sealed, and no private key here (${BACKUP_PRIVATE_KEY_FILE}): restore not proved"
    else
        fail "$(basename "$1"): not in the set"
    fi
}

# to_stdout <plain path> <sealed|plain>
to_stdout() { if [[ "$2" == sealed ]]; then open_file "$1.gpg"; else cat -- "$1"; fi; }

need_memory() {
    wait_for_memory 2000 || { fail "$1: not enough free memory for a scratch container"; return 1; }
}

# compare_tables <backup> <restored> <label>: line-for-line equality, the differing lines kept in the report
compare_exact() {
    if cmp -s "$1" "$2"; then return 0; fi
    note "  differing lines for $3 (< backup, > restored), first 20:"
    diff "$1" "$2" | grep '^[<>]' | head -n 20 | sed 's/^/  /' | tee -a "${report}" >/dev/null
    return 1
}

# drift_summary <at backup> <live now> <key columns>: what moved since the backup
drift_summary() {
    python3 -I - "$1" "$2" "$3" <<'PY'
import sys
at, live, keys = sys.argv[1], sys.argv[2], int(sys.argv[3])
def load(p):
    out = {}
    for line in open(p):
        parts = line.rstrip("\n").split("\t")
        out[tuple(parts[:keys])] = [int(v) for v in parts[keys:]]
    return out
a, b = load(at), load(live)
same = sum(1 for k in a if a[k] == b.get(k))
up = sum(1 for k in a if k in b and b[k] != a[k] and all(y >= x for x, y in zip(a[k], b[k])))
down = [k for k in a if k in b and b[k] != a[k] and not all(y >= x for x, y in zip(a[k], b[k]))]
print(f"same {same}, grown {up}, shrunk {len(down)}, new since {len(set(b) - set(a))}, gone since {len(set(a) - set(b))}")
PY
}

drill_postgres() {
    local dump counts t0 image
    dump="$(find "${PG_BACKUPS}" -maxdepth 1 -type f \( -name 'owl_db-[0-9]*-[0-9][0-9][0-9][0-9]Z.dump' -o -name 'owl_db-[0-9]*-[0-9][0-9][0-9][0-9]Z.dump.gpg' \) -printf '%f\n' | sed 's/\.gpg$//' | sort -u | tail -n 1)"
    [[ -n "${dump}" ]] || { fail "postgres: no dump in ${PG_BACKUPS}"; return; }
    counts="${PG_BACKUPS}/${dump%.dump}.counts.tsv"
    t0="$(date -u +%s)"
    how_to_read "${PG_BACKUPS}/${dump}"
    [[ "${HOW}" != locked ]] || return
    note "postgres: dump ${dump} ($(stored_size "${PG_BACKUPS}/${dump}") bytes, ${HOW}, hash checked in $(elapsed "${t0}") s)"
    local pg_how="${HOW}"
    need_memory postgres || return
    image="$("${DOCKER}" inspect "${PG_CONTAINER}" --format '{{.Image}}')"
    mkdir -p "${WORK}/pg"
    t0="$(date -u +%s)"
    "${DOCKER}" run -d --name "${SCRATCH_PG}" "${LIMITS[@]}" --network none -e POSTGRES_USER="${PG_USER}" -e POSTGRES_DB="${PG_DB}" \
        -e POSTGRES_HOST_AUTH_METHOD=trust -v "${WORK}/pg:/var/lib/postgresql/data" --entrypoint /usr/bin/nice "${image}" \
        -n 15 docker-entrypoint.sh postgres -c fsync=off -c full_page_writes=off -c synchronous_commit=off -c shared_buffers=256MB -c maintenance_work_mem=256MB >/dev/null ||
        { fail "postgres: scratch container did not start"; return; }
    local i
    for (( i = 0; i < 100; i++ )); do
        "${DOCKER}" exec "${SCRATCH_PG}" pg_isready -q -h 127.0.0.1 -U "${PG_USER}" -d "${PG_DB}" && break
        sleep 3
    done
    if ! to_stdout "${PG_BACKUPS}/${dump}" "${pg_how}" | "${DOCKER}" exec -i "${SCRATCH_PG}" nice -n 15 pg_restore -U "${PG_USER}" -d "${PG_DB}" --no-owner --no-privileges \
        > "${WORK}/pg_restore.log" 2>&1; then
        fail "postgres: pg_restore reported errors, first: $(grep -m1 -E 'error|ERROR' "${WORK}/pg_restore.log")"
    fi
    note "postgres: restored in $(elapsed "${t0}") s"
    run_counts() { "${DOCKER}" exec -i "$1" nice -n 15 psql -U "${PG_USER}" -d "${PG_DB}" -AtqX -F $'\t' < "${HERE}/pg-counts.sql" | LC_ALL=C sort; }
    run_counts "${SCRATCH_PG}" > "${WORK}/pg.restored.tsv"
    local lines rows
    lines="$(wc -l < "${WORK}/pg.restored.tsv")"
    rows="$(awk -F'\t' '{s += $3} END {print s + 0}' "${WORK}/pg.restored.tsv")"
    if [[ ! -s "${WORK}/pg.restored.tsv" ]]; then
        fail "postgres: no counts from the restored database"
    elif [[ ! -f "${counts}" ]]; then
        fail "postgres: ${dump} has no counts file to compare with"
    elif compare_exact "${counts}" "${WORK}/pg.restored.tsv" postgres; then
        pass "postgres: ${lines} table/case lines, ${rows} rows equal the counts read in the dump's snapshot"
    else
        fail "postgres: restored rows differ from the counts read in the dump's snapshot"
    fi
    run_counts "${PG_CONTAINER}" > "${WORK}/pg.live.tsv"
    [[ -s "${WORK}/pg.live.tsv" && -f "${counts}" ]] && note "postgres: live since the dump (table/case lines): $(drift_summary "${counts}" "${WORK}/pg.live.tsv" 2)"
    drill_evidence
    "${DOCKER}" rm -f "${SCRATCH_PG}" >/dev/null 2>&1
    rm -rf -- "${WORK}/pg"
}

drill_evidence() {
    local t0 checked=0 bad=0 copy_checked=0 copy_bad=0 id path sha got rel
    t0="$(date -u +%s)"
    # Every live row of the restored database names a file that is there; a row can name a folder (a phone extraction
    # is one row over its folder), which is checked by being there. Then a random sample of the files is hashed.
    "${DOCKER}" exec "${SCRATCH_PG}" psql -U "${PG_USER}" -d "${PG_DB}" -AtqX -F $'\t' -c \
        "SELECT id, stored_path, sha256 FROM evidence_files WHERE deleted_at IS NULL AND stored_path LIKE '/%' AND sha256 <> ''" > "${WORK}/rows.tsv"
    local rows folders=0 missing=0
    rows="$(wc -l < "${WORK}/rows.tsv")"
    : > "${WORK}/present.tsv"
    while IFS=$'\t' read -r id path sha; do
        if [[ -f "${path}" ]]; then printf '%s\t%s\t%s\n' "${id}" "${path}" "${sha}" >> "${WORK}/present.tsv"
        elif [[ -d "${path}" ]]; then folders=$(( folders + 1 ))
        else
            missing=$(( missing + 1 ))
            (( missing > 40 )) || note "  no file on disk: row ${id}"
        fi
    done < "${WORK}/rows.tsv"
    if (( rows == 0 )); then
        fail "evidence: the restored database named no files"
    elif (( missing )); then
        fail "evidence: ${missing} of ${rows} rows name a file that is not on disk ($(elapsed "${t0}") s)"
    else
        pass "evidence: all ${rows} rows name a file or folder that is on disk, ${folders} folders ($(elapsed "${t0}") s)"
    fi
    t0="$(date -u +%s)"
    while IFS=$'\t' read -r id path sha; do
        checked=$(( checked + 1 ))
        got="$(nice -n 15 sha256sum "${path}" | cut -d' ' -f1)"
        if [[ "${got}" != "${sha}" ]]; then bad=$(( bad + 1 )); note "  hash differs: row ${id}"; fi
        if [[ -n "${EVIDENCE_COPY_DEST}" ]]; then
            rel="${path#"${LIVE_CHECKOUT}/"}"; rel="${rel/#ingestion\/data/ingestion}"
            copy_checked=$(( copy_checked + 1 ))
            got="$(nice -n 15 sha256sum "${EVIDENCE_COPY_DEST}/files/${rel}" 2>/dev/null | cut -d' ' -f1)"
            [[ "${got}" == "${sha}" ]] || { copy_bad=$(( copy_bad + 1 )); note "  copy differs or is missing: row ${id}"; }
        fi
    done < <(shuf -n "${SAMPLE}" "${WORK}/present.tsv")
    if (( checked == 0 )); then
        fail "evidence: no file to sample"
    elif (( bad )); then
        fail "evidence: ${bad} hash differences in a sample of ${checked} ($(elapsed "${t0}") s)"
    else
        pass "evidence: ${checked} sampled files match the hash in the restored database at their live path ($(elapsed "${t0}") s)"
    fi
    if [[ -z "${EVIDENCE_COPY_DEST}" ]]; then
        note "evidence: copy not compared: no destination is set"
    elif (( copy_bad )); then
        fail "evidence copy: ${copy_bad} of ${copy_checked} sampled files differ or are missing in ${EVIDENCE_COPY_DEST}"
    else
        pass "evidence copy: ${copy_checked} sampled files match in ${EVIDENCE_COPY_DEST}"
    fi
}

drill_keys() {
    local set t0 bad=0 path size sha
    set="$(BACKUP_DIR="${KEYS_BACKUPS}" sets keys | tail -n 1)"
    [[ -n "${set}" ]] || { fail "keys: no set in ${KEYS_BACKUPS}"; return; }
    t0="$(date -u +%s)"
    mkdir -p "${WORK}/keys"
    if ! BACKUP_DIR="${KEYS_BACKUPS}" bash "${HERE}/keys-bundle.sh" open "${set}" "${WORK}/keys" > "${WORK}/keys.log" 2>&1; then
        fail "keys: ${set} did not open: $(tail -n 1 "${WORK}/keys.log" | cut -c1-200)"
        return
    fi
    while IFS=$'\t' read -r path size sha; do
        [[ "${size}" == missing ]] && continue
        [[ "$(sha256sum "${WORK}/keys/${path#/}" 2>/dev/null | cut -d' ' -f1)" == "${sha}" ]] || bad=$(( bad + 1 ))
    done < "${KEYS_BACKUPS}/${set}/files.tsv"
    if [[ ! -s "${KEYS_BACKUPS}/${set}/files.tsv" ]]; then
        fail "keys: ${set} has no list of files to compare with"
    elif (( bad )); then
        fail "keys: ${bad} files differ from ${set}/files.tsv"
    else
        pass "keys: ${set} opens, $(wc -l < "${KEYS_BACKUPS}/${set}/files.tsv") files equal its list ($(elapsed "${t0}") s)"
    fi
    rm -rf -- "${WORK}/keys"
}

plain_to_tsv() { tail -n +2 | tr -d '"' | sed 's/, /\t/g' | LC_ALL=C sort; }

drill_neo4j() {
    local set image t0 i ready=0 db
    set="$(BACKUP_DIR="${NEO4J_BACKUPS}" sets neo4j | tail -n 1)"
    [[ -n "${set}" ]] || { fail "neo4j: no set in ${NEO4J_BACKUPS}"; return; }
    local dir="${NEO4J_BACKUPS}/${set}" input="${NEO4J_BACKUPS}/${set}" f
    note "neo4j: set ${set} ($(stored_size "${dir}/neo4j.dump") bytes), $(grep -h counts_source "${dir}/meta.env")"
    need_memory neo4j || return
    image="$("${DOCKER}" inspect "${NEO4J_CONTAINER}" --format '{{.Image}}')"
    mkdir -p "${WORK}/n4j"
    t0="$(date -u +%s)"
    local -A how=()
    for f in neo4j.dump system.dump; do
        how_to_read "${dir}/${f}"
        [[ "${HOW}" != locked ]] || return
        how[${f}]="${HOW}"
        [[ "${HOW}" != sealed ]] || input="${WORK}/n4j-in"
    done
    if [[ "${input}" != "${dir}" ]]; then
        mkdir -p "${input}"
        for f in neo4j.dump system.dump; do
            to_stdout "${dir}/${f}" "${how[${f}]}" > "${input}/${f}" || { fail "neo4j: ${f} did not open"; return; }
        done
    fi
    note "neo4j: read in $(elapsed "${t0}") s ($( [[ "${input}" == "${dir}" ]] && echo plain || echo sealed))"
    admin() {
        "${DOCKER}" run --rm --name "${SCRATCH_N4J}-admin" --hostname localhost "${LIMITS[@]}" --network none \
            -v "${WORK}/n4j:/data" -v "${input}:/in:ro" --entrypoint /usr/bin/nice "${image}" -n 15 neo4j-admin "$@"
    }
    for db in neo4j system; do
        admin database load "${db}" --from-path=/in --overwrite-destination=true > "${WORK}/load-${db}.log" 2>&1 ||
            { fail "neo4j: load of ${db} failed: $(tail -n 1 "${WORK}/load-${db}.log" | cut -c1-200)"; return; }
    done
    note "neo4j: loaded in $(elapsed "${t0}") s"
    "${DOCKER}" run -d --name "${SCRATCH_N4J}" --hostname localhost "${LIMITS[@]}" --network none -e NEO4J_AUTH=none \
        -e NEO4J_server_memory_heap_initial__size=256m -e NEO4J_server_memory_heap_max__size=768m \
        -e NEO4J_server_memory_pagecache_size=512m -e NEO4J_db_transaction_timeout=0 -v "${WORK}/n4j:/data" \
        --entrypoint /usr/bin/nice "${image}" -n 15 tini -g -- /startup/docker-entrypoint.sh neo4j >/dev/null ||
        { fail "neo4j: scratch container did not start"; return; }
    for (( i = 0; i < 200; i++ )); do
        if echo 'RETURN 1;' | "${DOCKER}" exec -i "${SCRATCH_N4J}" cypher-shell --format plain >/dev/null 2>&1; then ready=1; break; fi
        sleep 3
    done
    (( ready )) || { fail "neo4j: scratch server did not come up"; return; }
    note "neo4j: up in $(elapsed "${t0}") s from the start of the load"
    printf '%s\n' "${COUNTS_QUERY}" | "${DOCKER}" exec -i "${SCRATCH_N4J}" nice -n 15 cypher-shell --format plain | plain_to_tsv > "${WORK}/n4j.restored.tsv"
    local lines nodes rels
    lines="$(wc -l < "${WORK}/n4j.restored.tsv")"
    nodes="$(awk -F'\t' '{s += $2} END {print s + 0}' "${WORK}/n4j.restored.tsv")"
    rels="$(awk -F'\t' '{s += $3} END {print s + 0}' "${WORK}/n4j.restored.tsv")"
    if [[ ! -s "${WORK}/n4j.restored.tsv" ]]; then
        fail "neo4j: no counts from the restored graph"
    elif compare_exact "${dir}/counts.tsv" "${WORK}/n4j.restored.tsv" neo4j; then
        pass "neo4j: ${lines} case lines, ${nodes} nodes, ${rels} relationships equal the counts read at the backup"
    else
        fail "neo4j: restored counts differ from the counts read at the backup"
    fi
    printf '%s\n' "${COUNTS_QUERY}" | "${DOCKER}" exec -i "${NEO4J_CONTAINER}" sh -c \
        'NEO4J_USERNAME="${NEO4J_AUTH%%/*}" NEO4J_PASSWORD="${NEO4J_AUTH#*/}" exec nice -n 15 cypher-shell --format plain' | plain_to_tsv > "${WORK}/n4j.live.tsv"
    [[ -s "${WORK}/n4j.live.tsv" ]] && note "neo4j: live since the backup (case lines): $(drift_summary "${dir}/counts.tsv" "${WORK}/n4j.live.tsv" 1)"
    "${DOCKER}" stop -t 120 "${SCRATCH_N4J}" >/dev/null 2>&1
    "${DOCKER}" rm -f "${SCRATCH_N4J}" >/dev/null 2>&1
    t0="$(date -u +%s)"
    if admin database check neo4j > "${WORK}/check.log" 2>&1; then
        pass "neo4j: consistency check clean ($(elapsed "${t0}") s)"
    else
        fail "neo4j: consistency check: $(tail -n 2 "${WORK}/check.log" | tr '\n' ' ' | cut -c1-240)"
    fi
    rm -rf -- "${WORK}/n4j" "${WORK}/n4j-in"
}

drill_chroma() {
    local set image t0 ip i ready=0
    set="$(BACKUP_DIR="${CHROMA_BACKUPS}" sets chroma | tail -n 1)"
    [[ -n "${set}" ]] || { fail "chroma: no set in ${CHROMA_BACKUPS}"; return; }
    local dir="${CHROMA_BACKUPS}/${set}"
    note "chroma: set ${set}"
    need_memory chroma || return
    image="$("${DOCKER}" inspect "${CHROMA_CONTAINER}" --format '{{.Image}}')"
    t0="$(date -u +%s)"
    mkdir -p "${WORK}/chroma"
    how_to_read "${dir}/hnsw.tar"; [[ "${HOW}" != locked ]] || return
    local index_how="${HOW}"
    how_to_read "${dir}/chroma.sqlite3"; [[ "${HOW}" != locked ]] || return
    note "chroma: indexes ${index_how}, database ${HOW}"
    if ! to_stdout "${dir}/hnsw.tar" "${index_how}" | tar -C "${WORK}/chroma" -xf - ||
        ! to_stdout "${dir}/chroma.sqlite3" "${HOW}" > "${WORK}/chroma/chroma.sqlite3"; then
        fail "chroma: the set did not unpack"
        return
    fi
    "${DOCKER}" run -d --name "${SCRATCH_CHROMA}" "${LIMITS[@]}" -v "${WORK}/chroma:/data" "${image}" >/dev/null ||
        { fail "chroma: scratch container did not start"; return; }
    ip="$("${DOCKER}" inspect "${SCRATCH_CHROMA}" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')"
    for (( i = 0; i < 100; i++ )); do
        curl -fsS -m 5 "http://${ip}:8000/api/v2/heartbeat" >/dev/null 2>&1 && { ready=1; break; }
        sleep 3
    done
    (( ready )) || { fail "chroma: scratch server did not come up"; return; }
    note "chroma: up in $(elapsed "${t0}") s"
    local out
    if out="$(python3 -I - "http://${ip}:8000" "${CHROMA_LIVE_URL}" "${API}" "${WORK}/chroma.restored.tsv" "${CHROMA_SAMPLE}" <<'PY'
import json, random, sys, urllib.request
restored, live, api, written, sample = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
def call(base, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"{base}/{api}/{path}", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)
rows, live_ids = {}, {c["name"]: c["id"] for c in call(live, "collections")}
tried = found_restored = found_live = 0
for c in call(restored, "collections"):
    count = rows[c["name"]] = call(restored, f"collections/{c['id']}/count")
    for offset in random.sample(range(count), min(sample, count)):
        got = call(restored, f"collections/{c['id']}/get", {"limit": 1, "offset": offset, "include": ["embeddings"]})
        if not got["ids"] or c["name"] not in live_ids:
            continue
        ask = {"query_embeddings": got["embeddings"], "n_results": 5, "include": []}
        tried += 1
        found_restored += got["ids"][0] in call(restored, f"collections/{c['id']}/query", ask)["ids"][0]
        found_live += got["ids"][0] in call(live, f"collections/{live_ids[c['name']]}/query", ask)["ids"][0]
with open(written, "w") as out:
    for name in sorted(rows):
        out.write(f"{name}\t{rows[name]}\n")
print(f"{tried} {found_restored} {found_live}")
PY
    )"; then
        if compare_exact <(LC_ALL=C sort "${dir}/counts.tsv") <(LC_ALL=C sort "${WORK}/chroma.restored.tsv") chroma; then
            pass "chroma: $(wc -l < "${dir}/counts.tsv") collections, $(awk -F'\t' '{s += $2} END {print s + 0}' "${dir}/counts.tsv") records equal the counts read at the backup"
        else
            fail "chroma: restored counts differ from the backup's"
        fi
        local tried found_restored found_live
        read -r tried found_restored found_live <<< "${out}"
        # Live is the yardstick: an approximate index does not find every stored vector on live either.
        if (( tried > 0 && found_restored >= found_live )); then
            pass "chroma: the restored index finds ${found_restored} of ${tried} stored vectors, live finds ${found_live}"
        else
            fail "chroma: the restored index finds ${found_restored} of ${tried} stored vectors, live finds ${found_live}"
        fi
    else
        fail "chroma: the restored server did not answer: ${out:-no output}"
    fi
    drill_chroma_reach "http://${ip}:8000"
    "${DOCKER}" rm -f "${SCRATCH_CHROMA}" >/dev/null 2>&1
    rm -rf -- "${WORK}/chroma"
}

drill_chroma_reach() {  # <url of the restored server>
    local t0 out reach
    t0="$(date -u +%s)"
    reach="${BACKUP_DIR}/.reach-$(stamp).json"
    # Every record, not a sample: an unreached passage is about 1 in 300, and a sample of 25 does not see it.
    if out="$(python3 -I "${HERE}/../backend/scripts/chroma_reach.py" check --url "$1" --out "${reach}" \
              --known "${REACH_KNOWN:-/mnt/owl-data/backups/chroma-relink/known.ids}" 2>&1)"; then
        pass "chroma: every stored record found by its own vector in $(elapsed "${t0}") s: ${out//$'\n'/; }"
        rm -f -- "${reach}"
    elif grep -q 'searched records unreached' <<< "${out}"; then
        mv -f -- "${reach}" "${reach/.reach-/reach-}"
        fail "chroma: stored records search cannot reach, listed in ${reach/.reach-/reach-}: ${out//$'\n'/; }"
    else
        fail "chroma: the reach check did not finish: ${out:-no output}"
    fi
}

do_run() {
    mkdir -p "${BACKUP_DIR}"
    exec 8>"${BACKUP_DIR}/.lock"
    flock -n 8 || { echo "a drill is already running" >&2; return 1; }
    local name t0 free_kb
    name="drill-$(stamp)Z.txt"
    report="${BACKUP_DIR}/.${name}.partial"
    : > "${report}"
    t0="$(date -u +%s)"
    trap cleanup EXIT
    cleanup
    mkdir -p "${WORK}"
    free_kb="$(df -Pk "${WORK}" | awk 'NR==2 {print $4}')"
    note "restore drill $(date -u +%FT%TZ), app $(git -c safe.directory='*' -C "${LIVE_CHECKOUT}" rev-parse --short HEAD 2>/dev/null)"
    if (( free_kb < 30 * 1024 * 1024 )); then
        fail "scratch disk: ${free_kb} KB free, 30 GB needed"
    else
        if [[ -f "${BACKUP_PRIVATE_KEY_FILE}" ]]; then
            open_begin "${BACKUP_PRIVATE_KEY_FILE}" || fail "the private key in ${BACKUP_PRIVATE_KEY_FILE} does not import"
        fi
        drill_keys
        drill_postgres
        drill_neo4j
        drill_chroma
    fi
    note "total $(elapsed "${t0}") s"
    if (( failures )); then note "RESULT FAIL (${failures})"; else note "RESULT PASS"; fi
    mv -f -- "${report}" "${BACKUP_DIR}/${name}"
    report="${BACKUP_DIR}/${name}"
    if (( failures )); then
        alert "restore drill FAILED (${failures}): see ${BACKUP_DIR}/${name}"
        return 1
    fi
}

do_check() {
    local newest age_d s
    newest="$(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'drill-[0-9]*Z.txt' -printf '%f\n' 2>/dev/null | sort | tail -n 1)"
    if [[ -z "${newest}" ]]; then
        alert "no restore drill in ${BACKUP_DIR}"
        return 1
    fi
    s="${newest#drill-}"; s="${s%Z.txt}"
    age_d=$(( ( $(now) - $(date -u -d "${s:0:8} ${s:9:2}:${s:11:2}" +%s) ) / 86400 ))
    if (( age_d >= DRILL_MAX_AGE_DAYS )); then
        alert "newest restore drill ${newest} is ${age_d} days old (limit ${DRILL_MAX_AGE_DAYS})"
        return 1
    fi
    if ! grep -q '^RESULT PASS' "${BACKUP_DIR}/${newest}"; then
        alert "newest restore drill ${newest} did not pass"
        return 1
    fi
    log "ok: newest ${newest}, ${age_d} days old, passed"
}

case "${1:-}" in
    run) do_run ;;
    check) do_check ;;
    *) echo "usage: $0 run|check" >&2; exit 2 ;;
esac
