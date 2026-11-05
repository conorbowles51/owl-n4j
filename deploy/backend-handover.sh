#!/usr/bin/env bash
# Replacing the backend with no wait (sourced by deploy.sh and rollback.sh, after backend-stop.sh and backend-socket.sh).
#
# A backend restart makes requests wait in the held port's queue until the new workers are up: 49-74 s on 4 Nov. With
# the switch at "handover" the unit's main process is deploy/backend_supervisor.py, and a release starts the next
# backend beside the running one on the same held socket. Nothing moves: nginx, the jobs and the health check keep
# using the API port. The old backend stops only when the new one has answered healthy from each worker and the
# ingestion gate has passed again; it finishes its requests within the same bounds as a service stop. A new backend that does not come up
# is stopped and the old one, never touched, keeps serving: the release is undone and the next one uses a restart.
#
# The switch: /etc/default/owl-backend-restart, else deploy/backend-restart.conf. The port must be held
# (deploy/backend-socket.conf). The first release after the switch restarts into the supervisor; the next can hand over.
# A plain restart remains the path for everything else: rollback, a changed .env or unit (the environment is read
# once, when the unit starts), a changed supervisor, and a migration an old backend cannot live with
# (deploy/migration_safety.py).
#
# The drop-in sorts after the socket's and names a copy of the supervisor outside the checkout, so a rollback to a commit
# without these files still starts. No Environment= and no RuntimeDirectory=: the financial views are saved under the
# service's environment (view_cache), and a new variable would make the release's prepared views miss.

BACKEND_SUPERVISOR_DIR="${BACKEND_SUPERVISOR_DIR:-/usr/local/lib/loupe}"
BACKEND_RESTART_SWITCH="${BACKEND_RESTART_SWITCH:-/etc/default/owl-backend-restart}"
BACKEND_HANDOVER_DROPIN_NAME="65-lx-restartwait-supervisor.conf"
BACKEND_HANDOVER_READY_LIMIT="${BACKEND_HANDOVER_READY_LIMIT:-330}"
BACKEND_HANDOVER_STOP_LIMIT="${BACKEND_HANDOVER_STOP_LIMIT:-100}"
BACKEND_HANDOVER_OPEN=false

backend_handover_state_file() { echo "${PROJECT_DIR}/deploy/logs/backend-supervisor.json"; }
backend_handover_fingerprint_file() { echo "${PROJECT_DIR}/deploy/logs/.backend-started-unit"; }
backend_handover_failed_file() { echo "${PROJECT_DIR}/deploy/logs/.backend-handover-failed"; }

backend_handover_wanted() {
    local wanted=""
    if [ -r "${BACKEND_RESTART_SWITCH}" ]; then
        wanted="$(grep -v '^[[:space:]]*\(#\|$\)' "${BACKEND_RESTART_SWITCH}" | head -1 | tr -d '[:space:]')"
    fi
    [ -n "${wanted}" ] ||
        wanted="$(grep -v '^[[:space:]]*\(#\|$\)' "${PROJECT_DIR}/deploy/backend-restart.conf" 2>/dev/null | head -1 | tr -d '[:space:]')"
    if [ "${wanted}" = handover ] && [ "$(backend_socket_wanted)" = held ]; then
        echo handover
    else
        echo restart
    fi
}

# The socket drop-in's ExecStart, with the supervisor in front of uvicorn.
backend_handover_exec_start() {
    local line
    line="$(backend_socket_exec_start)" || return 1
    case "${line}" in
        *"'exec "*"/uvicorn "*"'") ;;
        *) return 1 ;;
    esac
    printf '%s\n' "${line}" | sed -E "s#'exec ([^ ]+)/uvicorn (.*)'#'exec \1/python -I ${BACKEND_SUPERVISOR_DIR}/backend_supervisor.py --state $(backend_handover_state_file) -- \1/uvicorn \2'#"
}

backend_handover_remove() {
    local elevate=() dropin="${BACKEND_SOCKET_UNIT_DIR}/${BACKEND_UNIT}.service.d/${BACKEND_HANDOVER_DROPIN_NAME}"
    [ "$(id -u)" -ne 0 ] && elevate=(sudo)
    [ -e "${dropin}" ] || return 0
    "${elevate[@]}" rm -f -- "${dropin}"
    $SYSTEMCTL daemon-reload
}

# Called with the backend stopped, after backend_socket_apply. Never fails the restart: on any doubt the unit runs
# uvicorn itself, as before.
backend_handover_apply() {
    local exec_start changed="" elevate=()
    local dropin="${BACKEND_SOCKET_UNIT_DIR}/${BACKEND_UNIT}.service.d/${BACKEND_HANDOVER_DROPIN_NAME}"
    [ "$(id -u)" -ne 0 ] && elevate=(sudo)
    # A rollback goes back to the plain unit: if the supervisor is what failed, the way back must not depend on it.
    # The next release restarts into the supervisor again.
    if [ "$(backend_handover_wanted)" != handover ] || [ "${BACKEND_HANDOVER_ROLLING_BACK:-}" = true ]; then
        backend_handover_remove
        return 0
    fi
    # The socket may have just been given up (port busy, backend_socket_apply): --fd 3 needs it really there.
    if [ ! -e "${BACKEND_SOCKET_UNIT_DIR}/${BACKEND_UNIT}.service.d/${BACKEND_SOCKET_DROPIN_NAME}" ] ||
       ! exec_start="$(backend_handover_exec_start)"; then
        echo "  [WARN] No held port and uvicorn ExecStart to supervise; the unit runs the backend itself" >&2
        backend_handover_remove
        return 0
    fi
    if ! "${elevate[@]}" install -d -m 0755 "${BACKEND_SUPERVISOR_DIR}" ||
       ! "${elevate[@]}" install -m 0644 "${PROJECT_DIR}/deploy/backend_supervisor.py" "${BACKEND_SUPERVISOR_DIR}/.backend_supervisor.py.tmp" ||
       ! "${elevate[@]}" mv -f -- "${BACKEND_SUPERVISOR_DIR}/.backend_supervisor.py.tmp" "${BACKEND_SUPERVISOR_DIR}/backend_supervisor.py"; then
        echo "  [WARN] The supervisor could not be installed; a restart it stays" >&2
        backend_handover_remove
        return 0
    fi
    changed="$(backend_socket_install_file "${dropin}" "$(printf '# deploy/backend-handover.sh: the backend runs under the supervisor.\n[Service]\nExecStart=\n%s\n' "${exec_start}")")" || {
        echo "  [WARN] The supervisor drop-in could not be written; a restart it stays" >&2
        backend_handover_remove
        return 0
    }
    [ -n "${changed}" ] && $SYSTEMCTL daemon-reload
    echo "  [  OK] The backend runs under the supervisor (the next backend release can hand over)"
}

# What the running service read at its start: its unit with every drop-in, and the .env.
backend_handover_fingerprint() {
    { $SYSTEMCTL cat "${BACKEND_UNIT}" 2>/dev/null; cat "${ENV_FILE:-${PROJECT_DIR}/.env}" 2>/dev/null; } | sha256sum | cut -d' ' -f1
}

backend_handover_record_start() {
    backend_handover_fingerprint > "$(backend_handover_fingerprint_file)" 2>/dev/null || true
    rm -f "$(backend_handover_failed_file)"
}

backend_handover_field() {  # <name>: a number or string field of the top level or of the open handover
    sed -nE "s/.*\"$1\": \"?([^\",}]*)\"?.*/\1/p" "$(backend_handover_state_file)" 2>/dev/null | head -1
}

backend_handover_reason() {  # the whole text: it may hold commas and braces
    sed -nE 's/.*"reason": "(([^"\\]|\\.)*)".*/\1/p' "$(backend_handover_state_file)" 2>/dev/null | head -1
}

# Every reason a release must use a plain restart instead; says which.
backend_handover_possible() {
    local main state_pid
    [ "$(backend_handover_wanted)" = handover ] || return 1
    if [ -e "$(backend_handover_failed_file)" ]; then
        echo "  The last handover failed; this release restarts the backend"
        return 1
    fi
    main="$($SYSTEMCTL show -p MainPID --value "${BACKEND_UNIT}" 2>/dev/null)"
    state_pid="$(backend_handover_field pid)"
    if [ -z "${main}" ] || [ "${main}" != "${state_pid}" ]; then
        echo "  The backend does not run under the supervisor yet; this release restarts it into it"
        return 1
    fi
    if [ "$(backend_handover_field script_sha)" != "$(sha256sum "${PROJECT_DIR}/deploy/backend_supervisor.py" | cut -d' ' -f1)" ]; then
        echo "  The supervisor changed; this release restarts the backend"
        return 1
    fi
    if [ "$(cat "$(backend_handover_fingerprint_file)" 2>/dev/null)" != "$(backend_handover_fingerprint)" ]; then
        echo "  The unit or .env changed since the backend started; this release restarts it"
        return 1
    fi
}

backend_handover_signal() {
    $SYSTEMCTL kill --kill-whom=main --signal="$1" "${BACKEND_UNIT}"
}

# Waits until the handover numbered $1 is in one of the phases $2 (a | list), at most $3 seconds.
backend_handover_wait() {
    local id="$1" phases="$2" limit="$3" waited=0 phase
    while [ "${waited}" -lt "${limit}" ]; do
        if [ "$(backend_handover_field handovers)" = "${id}" ]; then
            phase="$(backend_handover_field phase)"
            if printf '%s\n' "${phases}" | tr '|' '\n' | grep -qx "${phase}"; then
                echo "${phase}"
                return 0
            fi
        fi
        sleep 1
        waited=$(( waited + 1 ))
    done
    echo timeout
}

backend_handover_give_up() {
    echo "  [WARN] Handover: $1" >&2
    printf '%s\n' "$1" > "$(backend_handover_failed_file)"
}

backend_handover_begin() {
    local before id phase
    before="$(backend_handover_field handovers)"
    id=$(( ${before:-0} + 1 ))
    BACKEND_HANDOVER_ID="${id}"
    if ! backend_handover_signal SIGUSR2; then
        backend_handover_give_up "the supervisor could not be signalled"
        return 1
    fi
    BACKEND_HANDOVER_OPEN=true
    echo "  Starting the next backend beside the running one..."
    phase="$(backend_handover_wait "${id}" 'ready|failed|done' "${BACKEND_HANDOVER_READY_LIMIT}")"
    case "${phase}" in
        ready|done) return 0 ;;
        failed)
            BACKEND_HANDOVER_OPEN=false
            backend_handover_give_up "$(backend_handover_reason)"
            return 1 ;;
        *)
            backend_handover_abort_open || true
            backend_handover_give_up "no answer from the supervisor after ${BACKEND_HANDOVER_READY_LIMIT} s"
            return 1 ;;
    esac
}

backend_handover_commit() {
    local phase
    if ! backend_handover_signal SIGHUP; then
        backend_handover_abort_open || true
        backend_handover_give_up "the supervisor could not be signalled to commit"
        return 1
    fi
    BACKEND_HANDOVER_OPEN=false
    phase="$(backend_handover_wait "${BACKEND_HANDOVER_ID}" 'done|failed' "${BACKEND_HANDOVER_STOP_LIMIT}")"
    if [ "${phase}" != done ]; then
        # The commit deadline or an ended backend got there first (failed), or the old one is slow to stop (timeout;
        # the supervisor still ends it, and the new one is serving).
        [ "${phase}" = failed ] && { backend_handover_give_up "$(backend_handover_reason)"; return 1; }
        echo "  [WARN] The old backend has not stopped after ${BACKEND_HANDOVER_STOP_LIMIT} s; the health check decides" >&2
    fi
    BACKEND_HANDED_OVER=true
    echo "  [  OK] The new backend took over (handover ${BACKEND_HANDOVER_ID})"
}

backend_handover_abort_open() {
    [ "${BACKEND_HANDOVER_OPEN}" = true ] || return 0
    BACKEND_HANDOVER_OPEN=false
    backend_handover_signal SIGQUIT
    echo "  Handover aborted: the old backend keeps serving"
}
