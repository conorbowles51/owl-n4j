#!/usr/bin/env bash
# The release's Chroma step with a fake reach tool: a relinked list leaves the daily reach verdict to be made again.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root:?}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export CHROMA_REACH_TOOL="${test_root}/reach.py" CHROMA_RELINK_LISTS="${test_root}/relink" \
    CHROMA_REBUILD_STATE="${test_root}/rebuild" REACH_STATE="${test_root}/reach.txt" DOCKER=false
mkdir "${CHROMA_RELINK_LISTS}"
cat > "${CHROMA_REACH_TOOL}" <<'PY'
import sys
if sys.argv[1] == "relink":
    print('{"before": 3, "ids": 1, "applied": true, "found": 1, "not_found": [], "after": 3, "unreached_after": []}')
PY
fail() { echo "FAIL: $*"; exit 1; }

# Nothing listed: the verdict stays.
echo "ALERT: stored records search cannot reach" > "${REACH_STATE}"
bash "${source_dir}/chroma-settings.sh" > "${test_root}/out" || fail "a release with no list failed"
[[ -f "${REACH_STATE}" ]] || fail "the verdict was dropped with nothing relinked"

# A known list is not a relink: the verdict stays.
echo "x" > "${CHROMA_RELINK_LISTS}/known.ids"
bash "${source_dir}/chroma-settings.sh" > "${test_root}/out" || fail "a release with known.ids failed"
[[ -f "${REACH_STATE}" ]] || fail "known.ids dropped the verdict"

# A list relinked: done, and the verdict that listed it is gone, so the next hourly check sweeps again.
echo "chunk-1" > "${CHROMA_RELINK_LISTS}/chunks.ids"
bash "${source_dir}/chroma-settings.sh" > "${test_root}/out" || fail "the relink release failed"
[[ -f "${CHROMA_RELINK_LISTS}/chunks.ids.done" && ! -e "${CHROMA_RELINK_LISTS}/chunks.ids" ]] || fail "list not done"
grep -q "chroma: relink chunks" "${test_root}/out" || fail "relink not reported"
[[ ! -e "${REACH_STATE}" ]] || fail "the out-of-date reach verdict was kept after a relink"
echo "test-chroma-settings: all passed"
