#!/usr/bin/env bash
# deploy/backend-tree.sh packages with real python, pip and git in a temporary folder: a release that changes
# backend/requirements.txt (pip=run). The running process keeps reading the old package; on a shared venv it reads the new.
set -euo pipefail
test_root="$(mktemp -d)"
sleepers=()
cleanup() { for pid in "${sleepers[@]:-}"; do [ -n "${pid}" ] && kill "${pid}" 2>/dev/null; done; rm -rf -- "${test_root}"; }
trap cleanup EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="${test_root}/app/checkout"
mkdir -p "${PROJECT_DIR}/deploy/logs" "${PROJECT_DIR}/backend/logs" "${PROJECT_DIR}/data" "${PROJECT_DIR}/evidence-data" \
    "${test_root}/cgroup/unit" "${test_root}/wheels"
: > "${test_root}/cgroup/unit/cgroup.procs"
cp "${source_dir}/backend-tree.conf" "${PROJECT_DIR}/deploy/"
echo A=1 > "${PROJECT_DIR}/.env"
printf '.env\ndeploy/logs\nbackend/logs\ndata\nevidence-data\n.venv\n__pycache__\n' > "${PROJECT_DIR}/.gitignore"
wheel() {  # a one-module wheel, version $1
    python3 - "$1" "${test_root}/wheels" <<'PY'
import sys, zipfile
version, folder = sys.argv[1:]
name = f'{folder}/pkgx-{version}-py3-none-any.whl'
with zipfile.ZipFile(name, 'w') as z:
    z.writestr('pkgx.py', f'VERSION = {version}\n')
    z.writestr(f'pkgx-{version}.dist-info/METADATA', f'Metadata-Version: 2.1\nName: pkgx\nVersion: {version}\n')
    z.writestr(f'pkgx-{version}.dist-info/WHEEL', 'Wheel-Version: 1.0\nGenerator: t\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
    z.writestr(f'pkgx-{version}.dist-info/RECORD', '')
PY
}
wheel 1; wheel 2
requirements() { printf -- '--no-index\n--find-links %s\npkgx==%s\n' "${test_root}/wheels" "$1" > "${PROJECT_DIR}/backend/requirements.txt"; }
cd "${PROJECT_DIR}"
git init -q -b main
gitc() { git -c user.name=t -c user.email=t@t "$@"; }
requirements 1; echo 1 > backend/code.py; git add -A; gitc commit -qm one; one="$(git rev-parse HEAD)"
echo 2 > backend/code.py; git add -A; gitc commit -qm two; same="$(git rev-parse HEAD)"
requirements 2; echo 3 > backend/code.py; git add -A; gitc commit -qm three; three="$(git rev-parse HEAD)"
git checkout -q "${one}"
python3 -m venv "${PROJECT_DIR}/.venv"
# A script in bin, as uvicorn is: it names the venv it lives in.
printf '#!%s/.venv/bin/python\nimport sys\nimport pkgx\nprint(sys.prefix, pkgx.VERSION)\n' "${PROJECT_DIR}" > .venv/bin/tool; chmod +x .venv/bin/tool
# Started as the unit starts uvicorn: a script in bin, reached through current/.venv. Its first line names the real folder.
printf '#!%s/.venv/bin/python\nimport sys\nsys.path.insert(0, ".")\nopen(sys.argv[1]).read()\nimport pkgx\nopen(sys.argv[2], "w").write(str(pkgx.VERSION))\n' "${PROJECT_DIR}" > .venv/bin/serve; chmod +x .venv/bin/serve
.venv/bin/python -m pip install -q -r backend/requirements.txt
VENV_DIR="${PROJECT_DIR}/.venv"; RUN_AS=""
BACKEND_SOCKET_UNIT_DIR="${test_root}/units"
BACKEND_UNIT=owl-backend-v2
BACKEND_CGROUP_ROOT="${test_root}/cgroup"
BACKEND_TREES="${test_root}/app/loupe-backend"
mkdir -p "${BACKEND_SOCKET_UNIT_DIR}/owl-backend-v2.service.d"
systemctl() { :; }
SYSTEMCTL=fake_systemctl
fake_systemctl() { case "$*" in show*ControlGroup*) echo /unit ;; esac; }
release_build_scope() { :; }
source "${source_dir}/backend-socket.sh"
source "${source_dir}/backend-tree.sh"
failures=0
check() { if [ "$2" = "$3" ]; then echo "ok: $1"; else echo "FAIL: $1 (got '$2', wanted '$3')"; failures=$((failures + 1)); fi; }

backend_tree_stage "${one}"
backend_tree_apply >/dev/null
check "the first tree links a venv of its own" "$(readlink "${BACKEND_TREES}/blue/.venv")" "../venvs/$(git rev-parse "${one}:backend/requirements.txt")"
check "the release tooling runs on the staged packages" "${VENV_DIR}" "$(readlink -f "${BACKEND_TREES}/blue/.venv")"
first_venv="${VENV_DIR}"
check "a script in bin names the folder its venv is really in" "$(head -1 "${first_venv}/bin/tool")" "#!${first_venv}/bin/python"
check "the checkout's venv keeps its own script" "$(head -1 "${PROJECT_DIR}/.venv/bin/tool")" "#!${PROJECT_DIR}/.venv/bin/python"
check "the unit's path reaches the package" "$("${BACKEND_TREES}/current/.venv/bin/tool" | cut -d' ' -f2)" 1
check "the running process's prefix is the real folder" "$("${BACKEND_TREES}/current/.venv/bin/tool" | cut -d' ' -f1)" "${first_venv}"

# A running backend started through current/.venv, which has not yet imported the package: a lazy import.
fifo="${test_root}/ask"; mkfifo "${fifo}"; answer="${test_root}/answer"
(cd "${BACKEND_TREES}/current/backend" && exec "${BACKEND_TREES}/current/.venv/bin/serve" "${fifo}" "${answer}") &
sleepers+=("$!"); echo "$!" >> "${test_root}/cgroup/unit/cgroup.procs"
sleep 0.3

backend_tree_stage "${same}"
check "the same package list needs no second venv" "$(ls "${BACKEND_TREES}/venvs" | wc -l | tr -d ' ')" 1
backend_tree_stage "${three}"
check "a changed list is built beside" "$(ls "${BACKEND_TREES}/venvs" | wc -l | tr -d ' ')" 2
check "the staged tree reads the new package" "$("${BACKEND_TREES}/green/.venv/bin/python" -c 'import pkgx; print(pkgx.VERSION)')" 2
check "the venv in use still holds the old package" "$("${first_venv}/bin/python" -c 'import pkgx; print(pkgx.VERSION)')" 1
check "unchanged files are shared, not copied" "$(stat -c %i "${first_venv}/lib/"python*/site-packages/pip/__init__.py)" \
    "$(stat -c %i "$(readlink -f "${BACKEND_TREES}/green/.venv")/lib/"python*/site-packages/pip/__init__.py)"
backend_tree_apply >/dev/null
echo go > "${fifo}"
for _ in $(seq 1 100); do [ -s "${answer}" ] && break; sleep 0.1; done
check "the old process, after the switch, reads the package of its own tree" "$(cat "${answer}")" 1
check "the backend now starts on the new package" "$("${BACKEND_TREES}/current/.venv/bin/python" -c 'import pkgx; print(pkgx.VERSION)')" 2

# A pip that fails leaves everything as it was and fails the stage.
git checkout -q "${three}"
printf -- '--no-index\npkgx==9\n' > backend/requirements.txt; git add -A; gitc commit -qm bad; bad="$(git rev-parse HEAD)"
sed -i '/./d' "${test_root}/cgroup/unit/cgroup.procs"; kill "${sleepers[0]}" 2>/dev/null || true
if backend_tree_stage "${bad}" 2>/dev/null; then check "a failed pip fails the stage" no yes; else check "a failed pip fails the stage" yes yes; fi
check "and leaves no half-built venv" "$(ls "${BACKEND_TREES}/venvs" | grep -c building || true)" 0
check "current still names working packages" "$("${BACKEND_TREES}/current/.venv/bin/python" -c 'import pkgx; print(pkgx.VERSION)')" 2

# Pruning keeps what the trees link to.
blue="$(readlink -f "${BACKEND_TREES}/blue/.venv")"; green="$(readlink -f "${BACKEND_TREES}/green/.venv")"
mkdir "${BACKEND_TREES}/venvs/old"
backend_venv_prune
check "an unlinked venv is removed" "$([ -e "${BACKEND_TREES}/venvs/old" ] && echo yes || echo no)" no
check "the trees' venvs stay" "$([ -d "${blue}" ] && [ -d "${green}" ] && echo yes)" yes

# The unit starts through current/.venv.
printf '[Service]\nExecStart=/bin/bash -lc '"'"'exec %s/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8002 --workers 2'"'"'\n' "${PROJECT_DIR}" > "${BACKEND_SOCKET_UNIT_DIR}/owl-backend-v2.service"
touch "${BACKEND_TREES}/current/.venv/bin/uvicorn"
check "the held-port ExecStart goes through current" "$(backend_socket_exec_start)" \
    "ExecStart=/bin/bash -lc 'exec ${BACKEND_TREES}/current/.venv/bin/uvicorn main:app --fd 3 --workers 2'"
echo checkout > "${PROJECT_DIR}/deploy/backend-tree.conf"
check "the way back keeps the unit's own venv" "$(backend_socket_exec_start)" \
    "ExecStart=/bin/bash -lc 'exec ${PROJECT_DIR}/.venv/bin/uvicorn main:app --fd 3 --workers 2'"

[ "${failures}" -eq 0 ] && echo "PASS backend venv" || { echo "${failures} FAILED"; exit 1; }
