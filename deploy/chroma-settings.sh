#!/usr/bin/env bash
# Keeps every stored passage findable by document search; deploy.sh runs it with the backend paused.
#   1. Search settings (backend/scripts/chroma_reach.py settings). The server reads them when it loads an index, so a
#      changed setting takes a restart of the Chroma container, about 10 s, inside the release's pause.
#   2. Records nothing links to, when CHROMA_RELINK_LISTS holds a list (<collection>.ids, from `chroma_reach.py check`;
#      known.ids beside them is the sweep's explained list and is never relinked):
#      each is re-added from its stored copy, and the list is kept as <collection>.ids.done with the result beside it.
#      A record still unreached is in the result and the printed line; it does not stop the release. A changed count does.
# A server that cannot be set or restarted stops the release.
set -uo pipefail
umask 077
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="${HERE}/../backend/scripts/chroma_reach.py"
CHROMA_URL="${CHROMA_URL:-http://127.0.0.1:8101}"
CHROMA_CONTAINER="${CHROMA_CONTAINER:-owl-v2-chromadb}"
CHROMA_RELINK_LISTS="${CHROMA_RELINK_LISTS:-/mnt/owl-data/backups/chroma-relink}"
DOCKER="${DOCKER:-docker}"
READY_TRIES="${READY_TRIES:-60}"

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
done
