#!/usr/bin/env bash
# The handover under real systemd on a throwaway port, as root, with the real uvicorn and a small app: a socket unit, a
# service unit with the supervisor in front, requests through the whole swap, a failed new backend, a plain restart, a
# stop. Removes its units. Never touches the live service. usage: rehearse-handover.sh <python of a venv with uvicorn>
set -euo pipefail
python="${1:?python with uvicorn}"
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit=loupe-handover-rehearsal
port=18765
work="$(mktemp -d /mnt/owl-data/tmp/rehearsal.XXXXXX)"
chmod 755 "${work}"
cleanup() {
    systemctl stop "${unit}.socket" "${unit}.service" 2>/dev/null || true
    rm -f "/etc/systemd/system/${unit}.socket" "/etc/systemd/system/${unit}.service"
    systemctl daemon-reload
    rm -rf -- "${work}"
}
trap cleanup EXIT
cp "${source_dir}/backend_supervisor.py" "${source_dir}/tests/handover_app.py" "${work}/"
echo ok > "${work}/mode"
cat > "/etc/systemd/system/${unit}.socket" <<UNIT
[Socket]
ListenStream=127.0.0.1:${port}
Backlog=2048
NoDelay=true
UNIT
cat > "/etc/systemd/system/${unit}.service" <<UNIT
[Unit]
Requires=${unit}.socket
After=${unit}.socket
[Service]
Type=simple
WorkingDirectory=${work}
Environment=HANDOVER_TEST_MODE=${work}/mode
Environment=UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=20
ExecStart=/bin/bash -lc 'exec ${python} -I ${work}/backend_supervisor.py --state ${work}/state.json -- ${python} -m uvicorn handover_app:app --fd 3 --workers 2 --log-level warning'
Restart=on-failure
RestartSec=2
TimeoutStopSec=90
UNIT
systemctl daemon-reload
systemctl start "${unit}.socket"
systemctl start "${unit}.service"
ask() { curl -s -m "${1:-5}" "http://127.0.0.1:${port}/health"; }
for _ in $(seq 1 240); do ask 2 | grep -q '"status": "ok"' && break; sleep 0.5; done
ask 2 | grep -q '"status": "ok"'
field() { sed -nE "s/.*\"$1\": \"?([^\",}]*)\"?.*/\1/p" "${work}/state.json" | head -1; }
wait_phase() {
    for _ in $(seq 1 1200); do
        [ "$(field handovers)" = "$1" ] && printf '%s\n' "$2" | tr '|' '\n' | grep -qx "$(field phase)" && return 0
        sleep 0.2
    done
    echo "phase not reached: $2; state: $(cat "${work}/state.json")" >&2
    return 1
}
main_before="$(systemctl show -p MainPID --value "${unit}")"
invocation="$(systemctl show -p InvocationID --value "${unit}")"
log="${work}/requests"
( while [ ! -e "${work}/stop" ]; do
    curl -s -o /dev/null -m 60 -w '%{http_code} %{time_total}\n' "http://127.0.0.1:${port}/health" >> "${log}" || echo "000 0" >> "${log}"
    sleep 0.02
  done ) &
client=$!
sleep 1
systemctl kill --kill-whom=main --signal=SIGUSR2 "${unit}"
wait_phase 1 'ready|failed'
test "$(field phase)" = ready
systemctl kill --kill-whom=main --signal=SIGHUP "${unit}"
wait_phase 1 'done'
sleep 2
touch "${work}/stop"; wait "${client}"; rm -f "${work}/stop"
total="$(wc -l < "${log}")"
bad="$(grep -vc '^200 ' "${log}" || true)"
slowest="$(sort -k2 -n "${log}" | tail -1 | cut -d' ' -f2)"
echo "handover: ${total} requests, ${bad} failed, slowest ${slowest} s"
test "${bad}" = 0
awk -v s="${slowest}" 'BEGIN{exit !(s < 2)}'
# One unit throughout: same main process, same invocation, active, every process in its cgroup.
test "$(systemctl show -p MainPID --value "${unit}")" = "${main_before}"
test "$(systemctl show -p InvocationID --value "${unit}")" = "${invocation}"
systemctl is-active -q "${unit}"

# A new backend that cannot import: the old one serves throughout, the release aborts it.
echo broken > "${work}/mode"
server="$(field server_pid)"
systemctl kill --kill-whom=main --signal=SIGUSR2 "${unit}"
sleep 5
ask 5 | grep -q "\"server\": ${server}"
systemctl kill --kill-whom=main --signal=SIGQUIT "${unit}"
wait_phase 2 'failed'
ask 5 | grep -q "\"server\": ${server}"
systemctl is-active -q "${unit}"
echo "failed new backend: old one serving, state: $(field reason)"
echo ok > "${work}/mode"

# A plain restart still works under the supervisor, with the port held.
systemctl restart "${unit}"
for _ in $(seq 1 240); do ask 2 | grep -q '"status": "ok"' && break; sleep 0.5; done
ask 2 | grep -q '"status": "ok"'
test "$(systemctl show -p MainPID --value "${unit}")" != "${main_before}"
echo "plain restart under the supervisor: ok"

# A stop ends every process of the unit, and a killed server is restarted by systemd.
kill -9 -- "-$(field server_pid)"
sleep 8
systemctl is-active -q "${unit}"
for _ in $(seq 1 240); do ask 2 | grep -q '"status": "ok"' && break; sleep 0.5; done
ask 2 | grep -q '"status": "ok"'
echo "killed server: systemd restarted the unit"
systemctl stop "${unit}.socket" "${unit}.service"
sleep 1
test "$(systemctl show -p TasksCurrent --value "${unit}")" = "[not set]" || test "$(systemctl show -p TasksCurrent --value "${unit}")" = 0 || systemctl show -p TasksCurrent --value "${unit}" | grep -qE '^(0|18446744073709551615|)$'
echo "rehearsal passed"
