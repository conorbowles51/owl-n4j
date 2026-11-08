#!/usr/bin/env bash
# frontend_prune keeps exactly the kept builds' assets in the pool, removes the rest in one pass, and when the
# serving build lists no assets it deletes nothing (a pool emptied against a misread kept set would 404 every
# open tab; the pre-8-Nov per-file loop emptied the pool in that state).
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
success() { :; }; step() { :; }; warn() { echo "warn: $*"; }; fail() { echo "fail: $*"; }
PROJECT_DIR="${test_root}"
RUN_AS=""
FRONTEND_RELEASES="${test_root}/loupe-frontend"
# shellcheck source=deploy/frontend-release.sh
source "${source_dir}/frontend-release.sh"
FRONTEND_KEEP_BUILDS=3

# Five builds, oldest to newest: old2, old1, c, b, a. Serving build is "a". Keep 3 -> a, b, c stay.
mkdir -p "${FRONTEND_RELEASES}/assets"
age=50
for b in old2 old1 c b a; do
    mkdir -p "${FRONTEND_RELEASES}/builds/${b}/assets"
    echo "commit=${b}" > "${FRONTEND_RELEASES}/builds/${b}/.loupe-build-complete"
    for f in "shared-everywhere.js" "only-${b}.js" "only-${b}.css"; do
        echo "${b}" > "${FRONTEND_RELEASES}/builds/${b}/assets/${f}"
        cp "${FRONTEND_RELEASES}/builds/${b}/assets/${f}" "${FRONTEND_RELEASES}/assets/${f}" 2>/dev/null || true
    done
    touch -d "@$(( $(date +%s) - age ))" "${FRONTEND_RELEASES}/builds/${b}"
    age=$((age - 10))
done
echo orphan > "${FRONTEND_RELEASES}/assets/orphan-from-a-long-gone-build.js"
ln -sfn "builds/a" "${FRONTEND_RELEASES}/current"

frontend_prune

for b in a b c; do
    [ -d "${FRONTEND_RELEASES}/builds/${b}" ] || { echo "kept build ${b} was removed"; exit 1; }
    for f in "only-${b}.js" "only-${b}.css" "shared-everywhere.js"; do
        [ -f "${FRONTEND_RELEASES}/assets/${f}" ] || { echo "kept asset ${f} was removed from the pool"; exit 1; }
    done
done
for b in old1 old2; do
    [ -e "${FRONTEND_RELEASES}/builds/${b}" ] && { echo "old build ${b} survived"; exit 1; }
    [ -e "${FRONTEND_RELEASES}/assets/only-${b}.js" ] && { echo "old build ${b}'s asset survived in the pool"; exit 1; }
done
[ -e "${FRONTEND_RELEASES}/assets/orphan-from-a-long-gone-build.js" ] && { echo "orphan asset survived"; exit 1; }
left="$(ls -1A "${FRONTEND_RELEASES}/assets" | LC_ALL=C sort)"
want="$(for b in a b c; do ls -1A "${FRONTEND_RELEASES}/builds/${b}/assets"; done | LC_ALL=C sort -u)"
[ "${left}" = "${want}" ] || { echo "pool is not exactly the kept builds' assets"; diff <(echo "${want}") <(echo "${left}") || true; exit 1; }

# The serving build listing no assets aborts with nothing deleted (the old loop emptied the pool here).
rm -rf "${FRONTEND_RELEASES}/builds/a/assets"
before="$(ls -1A "${FRONTEND_RELEASES}/assets" | LC_ALL=C sort)"
rc=0; frontend_prune || rc=$?
[ "${rc}" -ne 0 ] || { echo "prune with an unreadable serving build did not refuse"; exit 1; }
after="$(ls -1A "${FRONTEND_RELEASES}/assets" | LC_ALL=C sort)"
[ "${before}" = "${after}" ] || { echo "prune with an unreadable serving build deleted pool files"; exit 1; }

echo "test-frontend-prune: passed"
