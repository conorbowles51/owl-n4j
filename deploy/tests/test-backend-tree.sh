#!/usr/bin/env bash
# deploy/backend-tree.sh with real git and real processes in a temporary folder; a fake systemctl and control group.
set -euo pipefail
test_root="$(mktemp -d)"
sleepers=()
cleanup() { for pid in "${sleepers[@]:-}"; do [ -n "${pid}" ] && kill "${pid}" 2>/dev/null; done; rm -rf -- "${test_root}"; }
trap cleanup EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="${test_root}/app/checkout"
mkdir -p "${PROJECT_DIR}/deploy/logs" "${PROJECT_DIR}/backend/logs" "${PROJECT_DIR}/data" "${PROJECT_DIR}/evidence-data" \
    "${PROJECT_DIR}/venv/bin" "${test_root}/cgroup/unit"
: > "${test_root}/cgroup/unit/cgroup.procs"
cp "${source_dir}/backend-tree.conf" "${PROJECT_DIR}/deploy/"
echo A=1 > "${PROJECT_DIR}/.env"
printf '.env\ndeploy/logs\nbackend/logs\ndata\nevidence-data\nvenv\n' > "${PROJECT_DIR}/.gitignore"
cd "${PROJECT_DIR}"
git init -q -b main
gitc() { git -c user.name=t -c user.email=t@t "$@"; }
echo 1 > backend/code.py; git add -A; gitc commit -qm one; one="$(git rev-parse HEAD)"
echo 2 > backend/code.py; git add -A; gitc commit -qm two; two="$(git rev-parse HEAD)"
git checkout -q "${one}"
printf '#!/bin/bash\nmkdir -p "${@: -1}/compiled"\n' > venv/bin/python; chmod +x venv/bin/python
VENV_DIR="${PROJECT_DIR}/venv"; RUN_AS=""
BACKEND_SOCKET_UNIT_DIR="${test_root}/units"
BACKEND_CGROUP_ROOT="${test_root}/cgroup"
mkdir -p "${BACKEND_SOCKET_UNIT_DIR}/owl-backend-v2.service.d"
systemctl() { :; }
SYSTEMCTL=fake_systemctl
fake_systemctl() { case "$*" in show*ControlGroup*) echo /unit ;; esac; }
release_build_scope() { :; }
source "${source_dir}/backend-socket.sh"
source "${source_dir}/backend-tree.sh"
failures=0
check() { if [ "$2" = "$3" ]; then echo "ok: $1"; else echo "FAIL: $1 (got '$2', wanted '$3')"; failures=$((failures + 1)); fi; }
run_from() { (cd "$1" && exec sleep 300) & sleepers+=("$!"); echo "$!" >> "${test_root}/cgroup/unit/cgroup.procs"; }

backend_tree_stage "${one}"
check "the first stage takes blue" "${BACKEND_TREE_STAGED}" blue
check "blue holds the commit" "$(git -C "${BACKEND_TREES}/blue" rev-parse HEAD)" "${one}"
check "the prepare is told the folder" "${LOUPE_PREPARE_BACKEND_DIR}" "${BACKEND_TREES}/blue/backend"
check "the tree's .env is the checkout's" "$(cat "${BACKEND_TREES}/blue/.env")" "A=1"
check "the tree's logs are the checkout's" "$(readlink -f "${BACKEND_TREES}/blue/deploy/logs")" "$(readlink -f deploy/logs)"
check "links do not dirty the tree" "$(git -C "${BACKEND_TREES}/blue" status --porcelain --untracked-files=no)" ""
check "the tree is compiled" "$([ -d "${BACKEND_TREES}/blue/backend/compiled" ] && echo yes)" yes
backend_tree_apply >/dev/null
check "current names blue" "$(backend_tree_current)" blue
check "the unit starts from current" "$(grep WorkingDirectory "$(backend_tree_dropin)")" "WorkingDirectory=${BACKEND_TREES}/current/backend"

run_from "${BACKEND_TREES}/current/backend"
sleep 0.2
check "the running process is seen in blue" "$(backend_tree_in_use)" blue
git checkout -q "${two}"
backend_tree_stage "${two}"
check "the next stage takes green" "${BACKEND_TREE_STAGED}" green
check "blue did not move" "$(cat "${BACKEND_TREES}/blue/backend/code.py")" 1
check "green holds the new code" "$(cat "${BACKEND_TREES}/green/backend/code.py")" 2
backend_tree_stage "${two}"
check "staging again changes nothing" "${BACKEND_TREE_STAGED}" green
backend_tree_apply >/dev/null
check "the link moved under the running process" "$(backend_tree_current)" green
check "the process stays where it started" "$(backend_tree_in_use)" blue

# The old backend is still up and the release ends here (interrupted, or a handover undone).
backend_tree_settle
check "current goes back to what runs" "$(backend_tree_current)" blue

# A release stopped before its switch, then the next: the same free tree is used again.
backend_tree_stage "${two}"
check "a stage left over is reused" "${BACKEND_TREE_STAGED}" green

# Both trees in use is the one state nothing may move in.
run_from "${BACKEND_TREES}/green/backend"
sleep 0.2
if backend_tree_stage "${two}" 2>/dev/null; then check "both in use refuses" moved refused; else check "both in use refuses" refused refused; fi

# A failed new backend in green: the rollback serves the tree that ran, at the commit asked for.
kill "${sleepers[@]}" 2>/dev/null; wait 2>/dev/null || true; sleepers=(); : > "${test_root}/cgroup/unit/cgroup.procs"
backend_tree_stage "${two}"; backend_tree_apply >/dev/null
check "rollback starts from green" "$(backend_tree_current)" green
BACKEND_TREE_PREVIOUS=blue; BACKEND_TREE_APPLIED=true
backend_tree_rollback "${one}"
check "rollback points current at blue" "$(backend_tree_current)" blue
check "blue is at the rollback commit" "$(git -C "${BACKEND_TREES}/blue" rev-parse HEAD)" "${one}"

# The way back.
echo checkout > deploy/backend-tree.conf
backend_tree_apply
check "checkout mode removes the drop-in" "$([ -e "$(backend_tree_dropin)" ] && echo there || echo gone)" gone
backend_tree_stage "${two}"
check "checkout mode prepares in the checkout" "${LOUPE_PREPARE_BACKEND_DIR}" "${PROJECT_DIR}/backend"

[ "${failures}" -eq 0 ] && echo "test-backend-tree: all passed" || { echo "test-backend-tree: ${failures} failed"; exit 1; }
