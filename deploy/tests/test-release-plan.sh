#!/usr/bin/env bash
# Release plan and frontend build switching: a component is skipped only when its own inputs did not change; builds
# switch in one step; old builds' files stay reachable; pruning keeps the newest builds.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${here}/release-plan.sh"
scratch="$(mktemp -d)"
trap 'rm -rf "${scratch}"' EXIT
step() { :; }; success() { :; }; warn() { :; }; fail() { echo "FAIL: $*" >&2; }
RUN_AS=""
expect() { [ "$2" = "$3" ] || { echo "Expected $1 = $3, got $2"; exit 1; }; }
hash_of() { echo "$1" | sed -n "s/^$2=//p"; }

git init -q -b main "${scratch}/repo"
cd "${scratch}/repo"
git config user.name Test
git config user.email test@example.invalid
mkdir -p frontend_v2/src backend evidence-engine deploy
echo 'export const a = 1' > frontend_v2/src/a.ts
echo '{}' > frontend_v2/package-lock.json
echo 'fastapi' > backend/requirements.txt
echo 'x = 1' > backend/app.py
echo 'FROM python' > evidence-engine/Dockerfile
echo 'services: {}' > docker-compose.yml
printf 'A=1\nVITE_X=1\n' > "${scratch}/env"
git add -A && git commit -qm one
c1="$(git rev-parse HEAD)"
h1="$(release_component_hashes HEAD "${scratch}/env")"

# Same inputs, same hashes.
expect same-commit "$(release_component_hashes HEAD "${scratch}/env")" "${h1}"

# Backend-only commit: frontend and npm unchanged; backend and engine (which copies backend/) change.
echo 'x = 2' > backend/app.py
git commit -qam backend
h2="$(release_component_hashes HEAD "${scratch}/env")"
for c in frontend npm pip; do expect "backend-only ${c}" "$(hash_of "${h2}" "${c}")" "$(hash_of "${h1}" "${c}")"; done
for c in backend engine; do
    [ "$(hash_of "${h2}" "${c}")" != "$(hash_of "${h1}" "${c}")" ] || { echo "backend-only: ${c} should change"; exit 1; }
done

# Frontend-only commit: backend, engine and pip unchanged.
echo 'export const a = 2' > frontend_v2/src/a.ts
git commit -qam frontend
h3="$(release_component_hashes HEAD "${scratch}/env")"
for c in backend engine pip npm; do expect "frontend-only ${c}" "$(hash_of "${h3}" "${c}")" "$(hash_of "${h2}" "${c}")"; done
[ "$(hash_of "${h3}" frontend)" != "$(hash_of "${h2}" frontend)" ] || { echo "frontend-only: frontend should change"; exit 1; }

# A VITE_ setting reaches the bundle; any other .env change restarts the backend but does not rebuild the frontend.
printf 'A=1\nVITE_X=2\n' > "${scratch}/env2"
h4="$(release_component_hashes HEAD "${scratch}/env2")"
[ "$(hash_of "${h4}" frontend)" != "$(hash_of "${h3}" frontend)" ] || { echo "VITE_ change should rebuild"; exit 1; }
expect "vite-only backend" "$(hash_of "${h4}" backend)" "$(hash_of "${h3}" backend)"
printf 'A=2\nVITE_X=1\n' > "${scratch}/env3"
h5="$(release_component_hashes HEAD "${scratch}/env3")"
expect "env frontend" "$(hash_of "${h5}" frontend)" "$(hash_of "${h3}" frontend)"
[ "$(hash_of "${h5}" backend)" != "$(hash_of "${h3}" backend)" ] || { echo ".env change should restart backend"; exit 1; }

# Lock change: npm reinstall.
echo '{"x":1}' > frontend_v2/package-lock.json
git commit -qam lock
h6="$(release_component_hashes HEAD "${scratch}/env")"
[ "$(hash_of "${h6}" npm)" != "$(hash_of "${h3}" npm)" ] || { echo "lock change should reinstall"; exit 1; }

# Steps: skip only against a record of the live commit.
rec="${scratch}/components"
expect "no record" "$(release_step backend "${rec}" "${c1}" "${h1}")" run
release_record_write "${rec}" "${c1}" "${c1}" "${h1}"
expect "recorded, same" "$(release_step backend "${rec}" "${c1}" "${h1}")" skip
expect "recorded, changed" "$(release_step backend "${rec}" "${c1}" "${h2}")" run
expect "recorded, frontend same" "$(release_step frontend "${rec}" "${c1}" "${h2}")" skip
expect "live is another commit" "$(release_step backend "${rec}" "deadbeef" "${h1}")" run
expect "live unknown" "$(release_step backend "${rec}" "" "${h1}")" run
expect "summary" "$(release_plan_summary "${rec}" "${c1}" "${h2}")" "frontend=skip npm=skip pip=skip backend=run engine=run"

# The live release: the running backend's start commit explains it directly, or through the record of a release
# that did not restart the backend.
echo "${c1}" > "${scratch}/last-good"
expect "live direct" "$(release_live_commit "${c1}" "${scratch}/last-good" "${rec}")" "${c1}"
c3="$(git rev-parse HEAD~1)"
echo "${c3}" > "${scratch}/last-good"
release_record_write "${rec}" "${c3}" "${c1}" "${h3}"
expect "live via backend-skip record" "$(release_live_commit "${c1}" "${scratch}/last-good" "${rec}")" "${c3}"
expect "unexplained running backend" "$(release_live_commit "deadbeef" "${scratch}/last-good" "${rec}")" ""
expect "no running backend" "$(release_live_commit "" "${scratch}/last-good" "${rec}")" ""
expect "after a backend-skip release, skip against it" "$(release_step backend "${rec}" "${c3}" "${h3}")" skip

# Frontend builds: switch, asset pool, prune.
PROJECT_DIR="${scratch}/repo"
FRONTEND_RELEASES="${scratch}/releases"
FRONTEND_KEEP_BUILDS=2
FRONTEND_NGINX_SITE="${scratch}/no-site"
source "${here}/frontend-release.sh"
mkdir -p "${FRONTEND_RELEASES}/builds" "${FRONTEND_RELEASES}/assets"
fake_build() {
    local d="${FRONTEND_RELEASES}/builds/$1"
    mkdir -p "${d}/assets"
    echo "<html>$1</html>" > "${d}/index.html"
    echo "chunk $1" > "${d}/assets/chunk-$1.js"
    frontend_precompress "${d}"
    echo "commit=x" > "${d}/.loupe-build-complete"
    chmod -R a-w "${d}"
}
fake_build b1; frontend_switch b1
expect current "$(frontend_current_build)" b1
[ -f "${FRONTEND_RELEASES}/current/index.html.gz" ] || { echo "precompressed copy missing"; exit 1; }
gzip -dc "${FRONTEND_RELEASES}/current/index.html.gz" | cmp -s - "${FRONTEND_RELEASES}/current/index.html" ||
    { echo "gzip copy differs from the file"; exit 1; }
sleep 1; fake_build b2; frontend_switch b2
expect current "$(frontend_current_build)" b2
[ -f "${FRONTEND_RELEASES}/assets/chunk-b1.js" ] || { echo "old build's asset left the pool"; exit 1; }
[ -f "${FRONTEND_RELEASES}/assets/chunk-b2.js" ] || { echo "new build's asset not in the pool"; exit 1; }
if frontend_switch missing; then echo "switch to a missing build must fail"; exit 1; fi
expect "current after failed switch" "$(frontend_current_build)" b2
sleep 1; fake_build b3; frontend_switch b3
frontend_prune
[ -d "${FRONTEND_RELEASES}/builds/b3" ] && [ -d "${FRONTEND_RELEASES}/builds/b2" ] || { echo "prune removed a kept build"; exit 1; }
[ ! -e "${FRONTEND_RELEASES}/builds/b1" ] || { echo "prune kept too many builds"; exit 1; }
[ ! -e "${FRONTEND_RELEASES}/assets/chunk-b1.js" ] || { echo "pruned build's asset left in the pool"; exit 1; }
[ -f "${FRONTEND_RELEASES}/assets/chunk-b2.js" ] || { echo "kept build's asset pruned"; exit 1; }
chmod -R u+w "${FRONTEND_RELEASES}"
echo 'Release plan regression checks passed'
