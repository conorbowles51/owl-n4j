#!/usr/bin/env bash
# deploy/backend-handover.sh: real files in a temporary unit directory, a fake systemctl that records calls and answers as
# the supervisor would by writing its state file. No host unit is touched.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "${test_root}/deploy/logs" "${test_root}/units" "${test_root}/commands" "${test_root}/lib"
printf '#!/usr/bin/env bash\nexec "$@"\n' > "${test_root}/commands/sudo"
chmod +x "${test_root}/commands/sudo"
export PATH="${test_root}/commands:${PATH}"
PROJECT_DIR="${test_root}"
ENV_FILE="${test_root}/.env"; echo A=1 > "${ENV_FILE}"
API_PORT=8002
BACKEND_SOCKET_UNIT_DIR="${test_root}/units"
BACKEND_SUPERVISOR_DIR="${test_root}/lib"
BACKEND_RESTART_SWITCH="${test_root}/switch"
BACKEND_HANDOVER_READY_LIMIT=3
BACKEND_HANDOVER_STOP_LIMIT=3
calls="${test_root}/calls"
unit_state="${test_root}/state"
state_json="${test_root}/deploy/logs/backend-supervisor.json"
answer_to_usr2=ready
fake_systemctl() {
    printf '%s\n' "$*" >> "${calls}"
    case "$*" in
        show*InvocationID*) echo invocation-1 ;;
        show*MainPID*) echo 4242 ;;
        show*) cat "${unit_state}" ;;
        stop*) echo inactive > "${unit_state}" ;;
        start*) echo active > "${unit_state}" ;;
        cat*) cat "${test_root}/units/owl-backend-v2.service" ;;
        kill*SIGUSR2*) write_state 1 "${answer_to_usr2}" ;;
        kill*SIGHUP*) write_state 1 done ;;
        kill*SIGQUIT*) write_state 1 failed ;;
    esac
}
write_state() {
    printf '{"pid": 4242, "script_sha": "%s", "started_at": 1.5, "server_pid": 7, "handovers": %s, "handover": {"id": %s, "phase": "%s", "reason": "not healthy: {\047status\047: \047ok\047, \047neo4j\047: \047error: unavailable\047}"}}\n' \
        "$(sha256sum "${test_root}/deploy/backend_supervisor.py" | cut -d' ' -f1)" "$1" "$1" "$2" > "${state_json}"
}
SYSTEMCTL=fake_systemctl
BACKEND_POLL_INTERVAL=1
# shellcheck source=deploy/backend-stop.sh
source "${source_dir}/backend-stop.sh"
# shellcheck source=deploy/backend-socket.sh
source "${source_dir}/backend-socket.sh"
# shellcheck source=deploy/backend-handover.sh
source "${source_dir}/backend-tree.sh"
source "${source_dir}/backend-handover.sh"
cp "${source_dir}/backend_supervisor.py" "${test_root}/deploy/"
dropin="${test_root}/units/owl-backend-v2.service.d/65-lx-restartwait-supervisor.conf"
cat > "${test_root}/units/owl-backend-v2.service" <<'UNIT'
[Service]
ExecStart=/bin/bash -lc 'exec /venv/bin/uvicorn main:app --host 0.0.0.0 --port ${API_PORT:-8002} --workers 2'
UNIT
echo held > "${test_root}/deploy/backend-socket.conf"
echo active > "${unit_state}"

# Off (the default): the unit runs uvicorn itself and no release can hand over.
echo restart > "${test_root}/deploy/backend-restart.conf"
test "$(backend_handover_wanted)" = restart
restart_backend_bounded > /dev/null
test ! -e "${dropin}"
test ! -e "${test_root}/lib/backend_supervisor.py"
! backend_handover_possible > /dev/null

# The host file overrides the checkout, both ways; the port must be held.
echo handover > "${test_root}/switch"
test "$(backend_handover_wanted)" = handover
echo plain > "${test_root}/deploy/backend-socket.conf"
test "$(backend_handover_wanted)" = restart
echo held > "${test_root}/deploy/backend-socket.conf"
rm "${test_root}/switch"
echo handover > "${test_root}/deploy/backend-restart.conf"
test "$(backend_handover_wanted)" = handover
echo restart > "${test_root}/switch"
test "$(backend_handover_wanted)" = restart
rm "${test_root}/switch"

# On: the restart installs a copy of the supervisor outside the checkout and puts it in front of uvicorn, sorted after the
# socket's drop-in, with no environment of its own (the saved financial views are keyed on the service's environment).
: > "${calls}"
restart_backend_bounded > "${test_root}/out"
cmp "${source_dir}/backend_supervisor.py" "${test_root}/lib/backend_supervisor.py"
grep -qx "ExecStart=/bin/bash -lc 'exec /venv/bin/python -I ${test_root}/lib/backend_supervisor.py --state ${state_json} -- /venv/bin/uvicorn main:app --fd 3 --workers 2'" "${dropin}"
grep -qx 'ExecStart=' "${dropin}"
! grep -qE '^(Environment|RuntimeDirectory)' "${dropin}"
[[ "$(basename "${dropin}")" > "60-lx-release-socket.conf" ]]
test -s "${test_root}/deploy/logs/.backend-started-unit"
order="$(grep -nE '^(stop --no-block owl-backend-v2|start owl-backend-v2)$' "${calls}" | cut -d: -f2 | tr '\n' '|')"
test "${order}" = 'stop --no-block owl-backend-v2|start owl-backend-v2|'

# The socket given up (port busy): no --fd 3 under the supervisor, or the unit could not start.
hidden="${test_root}/held-dropin"
mv "${test_root}/units/owl-backend-v2.service.d/60-lx-release-socket.conf" "${hidden}"
backend_handover_apply > /dev/null 2>&1
test ! -e "${dropin}"
mv "${hidden}" "${test_root}/units/owl-backend-v2.service.d/60-lx-release-socket.conf"
backend_handover_apply > /dev/null
test -e "${dropin}"

# Possible only under the running supervisor, with what the service read at its start still current.
rm -f "${state_json}"
! backend_handover_possible > "${test_root}/out"
grep -q 'does not run under the supervisor' "${test_root}/out"
write_state 0 done
backend_handover_possible
echo B=2 >> "${ENV_FILE}"
! backend_handover_possible > "${test_root}/out"
grep -q 'unit or .env changed' "${test_root}/out"
sed -i '$d' "${ENV_FILE}"
backend_handover_possible
echo '# changed' >> "${test_root}/deploy/backend_supervisor.py"
! backend_handover_possible > "${test_root}/out"
grep -q 'supervisor changed' "${test_root}/out"
cp "${source_dir}/backend_supervisor.py" "${test_root}/deploy/"

# A handover: start, wait for ready, commit, done. Nothing stops the unit.
write_state 0 done
: > "${calls}"
backend_handover_begin > /dev/null
test "${BACKEND_HANDOVER_OPEN}" = true
backend_handover_commit > /dev/null
test "${BACKEND_HANDOVER_OPEN}" = false
test "${BACKEND_HANDED_OVER}" = true
test "$(grep -c 'SIGUSR2' "${calls}")" = 1
test "$(grep -c 'SIGHUP' "${calls}")" = 1
! grep -qE '^(stop|start) ' "${calls}"

# A new backend that fails: reported, not committed, and the next release restarts instead.
write_state 0 done
answer_to_usr2=failed
: > "${calls}"
! backend_handover_begin > /dev/null 2>&1
! grep -q SIGHUP "${calls}"
! grep -q SIGQUIT "${calls}"
! backend_handover_possible > "${test_root}/out"
grep -q 'last handover failed' "${test_root}/out"
grep -q "error: unavailable" "${test_root}/deploy/logs/.backend-handover-failed"
restart_backend_bounded > /dev/null
write_state 1 done
backend_handover_possible

# No answer from the supervisor within the limit: aborted, nothing committed.
write_state 1 done
answer_to_usr2=starting
: > "${calls}"
sysk() { printf '%s\n' "$*" >> "${calls}"; case "$*" in show*MainPID*) echo 4242;; esac; }
SYSTEMCTL=sysk
! backend_handover_begin > /dev/null 2>&1
grep -q SIGQUIT "${calls}"
! grep -q SIGHUP "${calls}"
SYSTEMCTL=fake_systemctl
rm -f "${test_root}/deploy/logs/.backend-handover-failed"

# A release that ends while a handover is open aborts it.
BACKEND_HANDOVER_OPEN=true
: > "${calls}"
backend_handover_abort_open > /dev/null
grep -q SIGQUIT "${calls}"
: > "${calls}"
backend_handover_abort_open > /dev/null
! grep -q SIGQUIT "${calls}"

# A rollback's restart leaves the supervisor out, whatever the switch says.
echo handover > "${test_root}/deploy/backend-restart.conf"
backend_handover_apply > /dev/null
test -e "${dropin}"
BACKEND_HANDOVER_ROLLING_BACK=true
backend_handover_apply > /dev/null
test ! -e "${dropin}"
BACKEND_HANDOVER_ROLLING_BACK=false

# Switched off again: the next restart puts the plain unit back.
echo restart > "${test_root}/deploy/backend-restart.conf"
restart_backend_bounded > /dev/null
test ! -e "${dropin}"
echo "backend handover: all checks passed"
