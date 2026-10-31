#!/usr/bin/env bash
# The API port held across a backend restart: real files in a temporary unit directory, a fake systemctl that
# records calls. No host unit is touched.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "${test_root}/deploy" "${test_root}/units" "${test_root}/commands"
printf '#!/usr/bin/env bash\nexec "$@"\n' > "${test_root}/commands/sudo"
chmod +x "${test_root}/commands/sudo"
export PATH="${test_root}/commands:${PATH}"
PROJECT_DIR="${test_root}"
API_PORT=8002
BACKEND_SOCKET_UNIT_DIR="${test_root}/units"
calls="${test_root}/calls"
unit_state="${test_root}/state"
socket_fails=no
fake_systemctl() {
    printf '%s\n' "$*" >> "${calls}"
    case "$1" in
        show) case "$*" in *InvocationID*) echo invocation-1 ;; *) cat "${unit_state}" ;; esac ;;
        stop) echo inactive > "${unit_state}" ;;
        start) echo active > "${unit_state}" ;;
        enable) [ "${socket_fails}" = no ] ;;
    esac
}
SYSTEMCTL=fake_systemctl
BACKEND_POLL_INTERVAL=1
# shellcheck source=deploy/backend-stop.sh
source "${source_dir}/backend-stop.sh"
# shellcheck source=deploy/backend-socket.sh
source "${source_dir}/backend-socket.sh"
sock="${test_root}/units/owl-backend-v2.socket"
dropin="${test_root}/units/owl-backend-v2.service.d/60-lx-release-socket.conf"
cat > "${test_root}/units/owl-backend-v2.service" <<'UNIT'
[Service]
ExecStart=/bin/bash -lc 'exec /venv/bin/uvicorn main:app --host 0.0.0.0 --port ${API_PORT:-8002} --workers 2'
UNIT

# held: the socket listens where the backend bound, uvicorn takes fd 3 with the same other arguments, and the
# socket is applied after the stop and before the start (the only moment the port is free).
echo held > "${test_root}/deploy/backend-socket.conf"
echo active > "${unit_state}"; : > "${calls}"
restart_backend_bounded > "${test_root}/out"
grep -qx 'ListenStream=0.0.0.0:8002' "${sock}"
grep -qx 'NoDelay=true' "${sock}"
grep -qx "ExecStart=/bin/bash -lc 'exec /venv/bin/uvicorn main:app --fd 3 --workers 2'" "${dropin}"
grep -qx 'ExecStart=' "${dropin}"
grep -qx 'Requires=owl-backend-v2.socket' "${dropin}"
order="$(grep -nE '^(stop --no-block owl-backend-v2|enable --now owl-backend-v2.socket|start owl-backend-v2)$' "${calls}" | cut -d: -f2 | tr '\n' '|')"
test "${order}" = 'stop --no-block owl-backend-v2|enable --now owl-backend-v2.socket|start owl-backend-v2|'
grep -q 'held by owl-backend-v2.socket' "${test_root}/out"
test "$(grep -c '^daemon-reload$' "${calls}")" = 1

# Repeating with nothing changed rewrites nothing and reloads nothing.
: > "${calls}"
restart_backend_bounded > /dev/null
test "$(grep -c '^daemon-reload$' "${calls}" || true)" = 0

# A port the socket cannot take restores the plain unit, and the backend still starts.
socket_fails=yes; : > "${calls}"
restart_backend_bounded > /dev/null 2> "${test_root}/err"
test ! -e "${sock}"; test ! -e "${dropin}"
grep -q 'not held' "${test_root}/err"
tail -1 "${calls}" | grep -qx 'start owl-backend-v2'
socket_fails=no

# plain (or no file) removes both and disables the socket; nothing to remove reloads nothing.
restart_backend_bounded > /dev/null
test -e "${sock}"
echo plain > "${test_root}/deploy/backend-socket.conf"; : > "${calls}"
restart_backend_bounded > /dev/null
test ! -e "${sock}"; test ! -e "${dropin}"
grep -qx 'disable --now owl-backend-v2.socket' "${calls}"
rm -f "${test_root}/deploy/backend-socket.conf"; : > "${calls}"
restart_backend_bounded > /dev/null
test "$(grep -c '^daemon-reload$' "${calls}" || true)" = 0

# A unit whose ExecStart has no --host/--port is left plain with a warning.
echo held > "${test_root}/deploy/backend-socket.conf"
printf '[Service]\nExecStart=/venv/bin/uvicorn main:app --uds /run/x.sock\n' > "${test_root}/units/owl-backend-v2.service"
restart_backend_bounded > /dev/null 2> "${test_root}/err"
test ! -e "${sock}"; test ! -e "${dropin}"
grep -q "no '--host H --port P'" "${test_root}/err"

# The repository's switch is "held", and a change to it or to the script restarts the backend (release plan).
test "$(PROJECT_DIR="${source_dir}/.." backend_socket_wanted)" = held
grep -q 'deploy/backend-socket.conf' "${source_dir}/release-plan.sh"
grep -q 'deploy/backend-socket.sh' "${source_dir}/release-plan.sh"
echo "test-backend-socket: passed"
