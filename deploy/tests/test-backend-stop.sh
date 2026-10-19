#!/usr/bin/env bash
# Bounded backend stop: a fake systemctl models a unit that stops cleanly,
# only on SIGINT, only on SIGKILL, or never. No host service is touched.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

unit_state_file="${test_root}/state"
calls="${test_root}/calls"
mode="${test_root}/mode"

fake_systemctl() {
    printf '%s\n' "$*" >> "${calls}"
    case "$1" in
        show) cat "${unit_state_file}" ;;
        stop)
            if [ "$(cat "${mode}")" = clean ]; then echo inactive > "${unit_state_file}"; else echo deactivating > "${unit_state_file}"; fi ;;
        kill)
            case "$(cat "${mode}"):$*" in
                sigint:*SIGINT*|sigkill:*SIGKILL*) echo inactive > "${unit_state_file}" ;;
            esac ;;
        start) echo active > "${unit_state_file}" ;;
    esac
}
fake_journalctl() { echo "fake journal: Waiting for background tasks to complete."; }

SYSTEMCTL=fake_systemctl
JOURNALCTL=fake_journalctl
BACKEND_STOP_TIMEOUT=2
BACKEND_SIGINT_GRACE=2
BACKEND_SIGKILL_GRACE=1
BACKEND_POLL_INTERVAL=1
# shellcheck source=deploy/backend-stop.sh
source "${source_dir}/backend-stop.sh"

run_case() {
    echo "$1" > "${mode}"
    echo active > "${unit_state_file}"
    : > "${calls}"
    local started rc=0
    started=$(date +%s)
    restart_backend_bounded > "${test_root}/out" 2>&1 || rc=$?
    ELAPSED=$(( $(date +%s) - started ))
    RC=${rc}
}

expect() {
    if ! grep -q -- "$1" "$2"; then
        echo "Expected '$1' in $2:" >&2
        cat "$2" >&2
        exit 1
    fi
}
refuse() {
    if grep -q -- "$1" "$2"; then
        echo "Unexpected '$1' in $2:" >&2
        cat "$2" >&2
        exit 1
    fi
}

# A clean stop never escalates and never waits.
run_case clean
test "${RC}" = 0
test "${BACKEND_STOP_ESCALATED}" = none
test "${ELAPSED}" -le 1
refuse kill "${calls}"
expect "stop --no-block owl-backend-v2" "${calls}"
expect "^start owl-backend-v2" "${calls}"

# A hung stop is escalated to SIGINT after the bound, with the log tail recorded.
run_case sigint
test "${RC}" = 0
test "${BACKEND_STOP_ESCALATED}" = sigint
test "${ELAPSED}" -le 4
expect "kill --kill-whom=all --signal=SIGINT owl-backend-v2" "${calls}"
refuse SIGKILL "${calls}"
expect "fake journal: Waiting for background tasks" "${test_root}/out"
expect "^start owl-backend-v2" "${calls}"

# SIGINT ignored: SIGKILL follows after its own bound.
run_case sigkill
test "${RC}" = 0
test "${BACKEND_STOP_ESCALATED}" = sigkill
test "${ELAPSED}" -le 7
expect "SIGINT" "${calls}"
expect "kill --kill-whom=all --signal=SIGKILL owl-backend-v2" "${calls}"
expect "^start owl-backend-v2" "${calls}"

# A unit that survives SIGKILL is reported, bounded, and not started twice.
run_case never
test "${RC}" = 1
test "${ELAPSED}" -le 8
refuse "^start" "${calls}"
expect "could not be stopped" "${test_root}/out"

echo 'bounded backend stop checks passed'
