#!/usr/bin/env bash
# Sourced before checkout changes, like ingestion-safety.sh, so a rollback to
# older code keeps the bounded stop.
#
# `systemctl restart` blocks for as long as the backend takes to stop, up to
# the unit's TimeoutStopSec. Uvicorn waits without limit for in-flight request
# tasks and a second SIGTERM does not force it, so one hung request held a
# deploy at "Restarting services" until someone sent SIGINT by hand, and the
# deploy never reached its health check, last-good marker or summary.
#
# restart_backend_bounded stops the unit without blocking, waits a bounded
# time, records the service log tail, then escalates: SIGINT to every process
# in the unit (Uvicorn's force-quit), then SIGKILL. Each step is bounded, so
# the deploy always continues to its health check and its log summary.
#
# Requires SYSTEMCTL (as deploy.sh/rollback.sh set it). Bounds are seconds.

BACKEND_UNIT="${BACKEND_UNIT:-owl-backend-v2}"
BACKEND_STOP_TIMEOUT="${BACKEND_STOP_TIMEOUT:-60}"
BACKEND_SIGINT_GRACE="${BACKEND_SIGINT_GRACE:-20}"
BACKEND_SIGKILL_GRACE="${BACKEND_SIGKILL_GRACE:-15}"
BACKEND_LOG_TAIL_LINES="${BACKEND_LOG_TAIL_LINES:-80}"
BACKEND_POLL_INTERVAL="${BACKEND_POLL_INTERVAL:-1}"
JOURNALCTL="${JOURNALCTL:-journalctl}"

backend_active_state() {
    $SYSTEMCTL show -p ActiveState --value "${BACKEND_UNIT}" 2>/dev/null || echo unknown
}

# Succeeds once the unit has no running processes left (inactive or failed).
wait_backend_stopped() {
    local limit="$1"
    local waited=0
    local state
    while :; do
        state="$(backend_active_state)"
        case "${state}" in
            inactive|failed) return 0 ;;
        esac
        if [ "${waited}" -ge "${limit}" ]; then
            echo "  backend still ${state} after ${limit}s"
            return 1
        fi
        sleep "${BACKEND_POLL_INTERVAL}"
        waited=$(( waited + BACKEND_POLL_INTERVAL ))
    done
}

record_backend_log_tail() {
    echo "  ---- last ${BACKEND_LOG_TAIL_LINES} lines of ${BACKEND_UNIT} ----"
    $JOURNALCTL -u "${BACKEND_UNIT}" -n "${BACKEND_LOG_TAIL_LINES}" --no-pager -o short-iso 2>&1 || \
        echo "  (journal unavailable)"
    echo "  ---- end of ${BACKEND_UNIT} log ----"
}

stop_backend_bounded() {
    BACKEND_STOP_ESCALATED=none
    $SYSTEMCTL stop --no-block "${BACKEND_UNIT}" || return 1
    if wait_backend_stopped "${BACKEND_STOP_TIMEOUT}"; then
        return 0
    fi
    BACKEND_STOP_ESCALATED=sigint
    echo "  ${BACKEND_UNIT} did not stop within ${BACKEND_STOP_TIMEOUT}s; its log shows what was pending:"
    record_backend_log_tail
    echo "  Sending SIGINT (Uvicorn force-quit) to every ${BACKEND_UNIT} process"
    $SYSTEMCTL kill --kill-whom=all --signal=SIGINT "${BACKEND_UNIT}" || true
    if wait_backend_stopped "${BACKEND_SIGINT_GRACE}"; then
        return 0
    fi
    BACKEND_STOP_ESCALATED=sigkill
    echo "  Still running ${BACKEND_SIGINT_GRACE}s after SIGINT; sending SIGKILL"
    $SYSTEMCTL kill --kill-whom=all --signal=SIGKILL "${BACKEND_UNIT}" || true
    wait_backend_stopped "${BACKEND_SIGKILL_GRACE}"
}

# Never blocks longer than the sum of the bounds above plus the start itself.
restart_backend_bounded() {
    if ! stop_backend_bounded; then
        echo "  ${BACKEND_UNIT} could not be stopped (escalation: ${BACKEND_STOP_ESCALATED:-none}); not starting a second copy"
        return 1
    fi
    if [ "${BACKEND_STOP_ESCALATED}" != none ]; then
        echo "  ${BACKEND_UNIT} stopped after escalation (${BACKEND_STOP_ESCALATED}); durable work resumes on start"
    fi
    $SYSTEMCTL start "${BACKEND_UNIT}"
}
