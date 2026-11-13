#!/usr/bin/env bash
# Keeps every stored passage findable by document search; deploy.sh runs it with the backend paused.
#   1. Search settings (backend/scripts/chroma_reach.py settings). The server reads them when it loads an index, so a
#      changed setting takes a restart of the Chroma container, about 10 s, inside the release's pause.
#   2. Records nothing links to, when CHROMA_RELINK_LISTS holds a list (<collection>.ids, from `chroma_reach.py check`;
#      known.ids beside them is the sweep's explained list and is never relinked):
#      each is re-added from its stored copy, and the list is kept as <collection>.ids.done with the result beside it.
#      A record still unreached is in the result and the printed line; it does not stop the release. A changed count does.
#   3. Collections made with too few links per record (chroma_reach.py MAX_NEIGHBORS) are built again from their
#      stored records and swapped in (`rebuild`); the old one stays as <name>__before_rebuild. `chroma-settings.sh
#      catch-up`, run by deploy.sh once the backend has restarted, carries over what the old backend wrote to the old
#      one meanwhile; the next release removes the old one. A rebuild that does not check out is refused and changes
#      nothing. State in CHROMA_REBUILD_STATE.
# A server that cannot be set or restarted stops the release.
set -uo pipefail
umask 077
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="${CHROMA_REACH_TOOL:-${HERE}/../backend/scripts/chroma_reach.py}"
CHROMA_URL="${CHROMA_URL:-http://127.0.0.1:8101}"
CHROMA_CONTAINER="${CHROMA_CONTAINER:-owl-v2-chromadb}"
CHROMA_RELINK_LISTS="${CHROMA_RELINK_LISTS:-/mnt/owl-data/backups/chroma-relink}"
# The daily reach verdict backup-check.sh reuses (its REACH_STATE). A relink makes it out of date.
REACH_STATE="${REACH_STATE:-/mnt/owl-data/backups/chroma-reach.txt}"
DOCKER="${DOCKER:-docker}"
READY_TRIES="${READY_TRIES:-60}"
CHROMA_REBUILD_STATE="${CHROMA_REBUILD_STATE:-/mnt/owl-data/backups/chroma-rebuild}"
mkdir -p "${CHROMA_REBUILD_STATE}"

rebuild_step() {  # catch-up | clean-up | rebuild
    local extra=()
    [[ "$1" == rebuild ]] && extra=(--apply)
    python3 -I "${TOOL}" "$1" --url "${CHROMA_URL}" --state "${CHROMA_REBUILD_STATE}" "${extra[@]}" |
        sed "s/^/chroma: $1 /"
    return "${PIPESTATUS[0]}"
}

if [[ "${1:-}" == catch-up ]]; then
    rebuild_step catch-up
    exit
fi

ready() {
    local try
    for (( try = 0; try < READY_TRIES; try++ )); do
        curl -fsS -m 5 "${CHROMA_URL}/api/v2/heartbeat" >/dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}

python3 -I "${TOOL}" settings --url "${CHROMA_URL}" --apply
status=$?
if (( status == 10 )); then
    echo "chroma: settings changed, restarting ${CHROMA_CONTAINER}"
    "${DOCKER}" restart "${CHROMA_CONTAINER}" >/dev/null || { echo "chroma: restart failed" >&2; exit 1; }
    ready || { echo "chroma: did not come back after the restart" >&2; exit 1; }
elif (( status != 0 )); then
    echo "chroma: settings could not be read or written" >&2
    exit 1
fi

# A catch-up the last release did not reach runs first; a caught-up old collection is then removed.
rebuild_step catch-up || { echo "chroma: catch-up after a rebuild failed" >&2; exit 1; }
rebuild_step clean-up || { echo "chroma: clean-up after a rebuild failed" >&2; exit 1; }
rebuild_step rebuild || { echo "chroma: rebuild failed part way; see the line above" >&2; exit 1; }

for list in "${CHROMA_RELINK_LISTS}"/*.ids; do
    [[ -f "${list}" ]] || continue
    collection="$(basename "${list}" .ids)"
    # known.ids is the reach sweep's list of records already explained (backup-check.sh REACH_KNOWN), not a relink
    # list: read as one it named a collection "known" and stopped every release (8 Nov 12:46-14:12).
    [[ "${collection}" == known ]] && continue
    python3 -I "${TOOL}" relink --url "${CHROMA_URL}" --collection "${collection}" --ids "${list}" \
        --keep "${list}.records.jsonl" --apply \
        > "${list}.result" || { echo "chroma: relink of ${collection} failed: $(cat "${list}.result")" >&2; exit 1; }
    mv -f -- "${list}" "${list}.done"
    echo "chroma: relink ${collection}: $(cat "${list}.result")"
    relinked=1
done
# The verdict that listed these records is now out of date. Removed, the next hourly backup-check sweeps again, so the
# board shows the repair within the hour instead of the old alert until the day is up (12 Nov 2026: 58 relinked at
# 20:09, the alert stayed until the next sweep at 20:51 the day after).
if [[ -n "${relinked:-}" ]]; then
    rm -f -- "${REACH_STATE}"
fi
