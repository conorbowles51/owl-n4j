#!/usr/bin/env bash
# The API port held open across a backend restart (sourced by deploy.sh and rollback.sh; called by
# restart_backend_bounded between the stop and the start, the only moment the port is free).
#
# Without it the port is closed from the old backend's "Shutting down" until the new workers listen, 11-14 s per
# release (measured 31 Oct), and every request in that window is refused (502 through :5174). With
# deploy/backend-socket.conf = "held", systemd owns the listening socket (owl-backend-v2.socket) and hands it to
# uvicorn (--fd 3): during a restart requests wait in the kernel's queue and are answered by the new workers.
# Nothing runs twice: one backend at a time, as before.
#
# "plain" (or no file) removes the socket unit and the drop-in, so uvicorn binds the port itself again; the next
# release applies it. Trade-off: while no backend can start at all, a request waits instead of failing fast.
# While the socket is active a request starts a stopped backend (backend-stop.sh treats that new instance as the
# end of the stop); to keep it down: systemctl stop owl-backend-v2.socket owl-backend-v2.
# NoDelay: uvicorn opens an --fd socket as AF_UNIX and so never sets TCP_NODELAY; set on the listening socket, every
# accepted connection inherits it, as with --host/--port.

BACKEND_SOCKET_UNIT_DIR="${BACKEND_SOCKET_UNIT_DIR:-/etc/systemd/system}"
BACKEND_SOCKET_DROPIN_NAME="60-lx-release-socket.conf"

backend_socket_wanted() {
    local wanted
    wanted="$(grep -v '^[[:space:]]*\(#\|$\)' "${PROJECT_DIR}/deploy/backend-socket.conf" 2>/dev/null | head -1 | tr -d '[:space:]')"
    case "${wanted}" in
        held) echo held ;;
        *) echo plain ;;
    esac
}

# The base unit's ExecStart with "--host H --port P" replaced by "--fd 3"; fails when the unit has no such line.
backend_socket_exec_start() {
    local line
    line="$(grep '^ExecStart=' "${BACKEND_SOCKET_UNIT_DIR}/${BACKEND_UNIT}.service" 2>/dev/null | tail -1)"
    case "${line}" in
        *" --host "*" --port "*) ;;
        *) return 1 ;;
    esac
    printf '%s\n' "${line}" | sed -E 's/ --host [^ ]+ --port [^ ]+/ --fd 3/'
}

# The listening address the backend binds today: its --host and API_PORT.
backend_socket_listen() {
    local host
    host="$(grep '^ExecStart=' "${BACKEND_SOCKET_UNIT_DIR}/${BACKEND_UNIT}.service" 2>/dev/null | tail -1 |
        sed -nE 's/.* --host ([^ ]+) --port .*/\1/p')"
    [ -n "${host}" ] || return 1
    printf '%s:%s\n' "${host}" "${API_PORT:-8002}"
}

backend_socket_render_socket() {
    printf '[Unit]\nDescription=Loupe API port, held open across backend restarts (deploy/backend-socket.sh)\n\n'
    printf '[Socket]\nListenStream=%s\nBacklog=2048\nNoDelay=true\n\n[Install]\nWantedBy=sockets.target\n' "$1"
}

backend_socket_render_dropin() {
    printf '# deploy/backend-socket.sh: uvicorn serves the socket systemd holds open (owl-backend-v2.socket).\n'
    printf '[Unit]\nRequires=%s.socket\nAfter=%s.socket\n\n[Service]\nExecStart=\n%s\n' \
        "${BACKEND_UNIT}" "${BACKEND_UNIT}" "$1"
}

# Writes $2 to $1 through a temporary file and mv; prints "changed" when the content differed.
backend_socket_install_file() {
    local target="$1" content="$2" elevate=() tmp
    [ "$(id -u)" -ne 0 ] && elevate=(sudo)
    if [ -e "${target}" ] && [ "$(cat "${target}")" = "${content}" ]; then
        return 0
    fi
    tmp="$(dirname "${target}")/.$(basename "${target}").tmp"
    "${elevate[@]}" install -d -m 0755 "$(dirname "${target}")" &&
        printf '%s\n' "${content}" | "${elevate[@]}" tee "${tmp}" >/dev/null &&
        "${elevate[@]}" chmod 0644 "${tmp}" &&
        "${elevate[@]}" mv -f -- "${tmp}" "${target}" || { "${elevate[@]}" rm -f -- "${tmp}"; return 1; }
    echo changed
}

backend_socket_remove() {
    local elevate=() dropin="${BACKEND_SOCKET_UNIT_DIR}/${BACKEND_UNIT}.service.d/${BACKEND_SOCKET_DROPIN_NAME}"
    local sock="${BACKEND_SOCKET_UNIT_DIR}/${BACKEND_UNIT}.socket"
    [ "$(id -u)" -ne 0 ] && elevate=(sudo)
    [ -e "${dropin}" ] || [ -e "${sock}" ] || return 0
    "${elevate[@]}" rm -f -- "${dropin}"
    if [ -e "${sock}" ]; then
        $SYSTEMCTL disable --now "${BACKEND_UNIT}.socket" 2>/dev/null || true
        "${elevate[@]}" rm -f -- "${sock}"
    fi
    $SYSTEMCTL daemon-reload
}

# Called with the backend stopped. Never fails the restart: when the socket cannot be held, the plain unit is
# restored so the start that follows binds the port as before.
backend_socket_apply() {
    local exec_start listen changed=""
    local dropin="${BACKEND_SOCKET_UNIT_DIR}/${BACKEND_UNIT}.service.d/${BACKEND_SOCKET_DROPIN_NAME}"
    if [ "$(backend_socket_wanted)" != held ]; then
        backend_socket_remove
        echo "  [  OK] API port: bound by the backend (refused while it restarts)"
        return 0
    fi
    if ! exec_start="$(backend_socket_exec_start)" || ! listen="$(backend_socket_listen)"; then
        echo "  [WARN] ${BACKEND_UNIT}.service has no '--host H --port P' ExecStart; the API port is not held" >&2
        backend_socket_remove
        return 0
    fi
    changed+="$(backend_socket_install_file "${BACKEND_SOCKET_UNIT_DIR}/${BACKEND_UNIT}.socket" \
        "$(backend_socket_render_socket "${listen}")")" || changed+=failed
    changed+="$(backend_socket_install_file "${dropin}" "$(backend_socket_render_dropin "${exec_start}")")" || changed+=failed
    case "${changed}" in *failed*)
        echo "  [WARN] The socket unit could not be written; the API port is not held" >&2
        backend_socket_remove
        return 0 ;;
    esac
    [ -n "${changed}" ] && $SYSTEMCTL daemon-reload
    if ! $SYSTEMCTL enable --now "${BACKEND_UNIT}.socket"; then
        echo "  [WARN] ${BACKEND_UNIT}.socket did not start (port ${listen} busy?); the API port is not held" >&2
        backend_socket_remove
        return 0
    fi
    echo "  [  OK] API port ${listen}: held by ${BACKEND_UNIT}.socket (requests wait during the restart)"
}
