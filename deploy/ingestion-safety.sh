#!/usr/bin/env bash
# Sourced before checkout changes. Keep the verified gate/function definitions
# in this shell so a rollback to older code cannot weaken its own safety checks.
INGESTION_GATE_CODE="$(cat "${PROJECT_DIR}/deploy/check_ingestion_idle.py")"

check_ingestion_idle() {
    $RUN_AS "${VENV_DIR}/bin/python" -c "${INGESTION_GATE_CODE}" "${BACKEND_DIR}"
}

configure_ingestion_shutdown() {
    local elevate=()
    local source_file
    local unit_dir=/etc/systemd/system/owl-backend-v2.service.d
    if [ "$(id -u)" -ne 0 ]; then
        elevate=(sudo)
    fi
    # Bounded stop. Uvicorn cancels request tasks still running 20s after
    # SIGTERM (it otherwise waits forever), the lifespan abandons background
    # units after 10s more, and the app's watchdog ends the process 45s after
    # the first signal. Abandoned financial units are durable (leased batches,
    # pending recovery items, revisioned graph sweeps) and resume on the next
    # start; deploys only restart after the ingestion gate reports idle.
    # systemd's SIGKILL at 90s is the backstop. Reloading this changes no
    # running service or job; it applies to the next stop and start.
    # Service runners need not provide /dev/stdin. A regular temporary source
    # also survives privilege elevation without reopening a process fd.
    source_file="$(mktemp)" || return 1
    if ! cat > "${source_file}" <<'UNIT'
[Service]
TimeoutStopSec=90
Environment=UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN=20
UNIT
    then
        rm -f -- "${source_file}"
        return 1
    fi
    if ! "${elevate[@]}" install -d -m 0755 "${unit_dir}"; then
        rm -f -- "${source_file}"
        return 1
    fi
    if ! "${elevate[@]}" install -m 0644 "${source_file}" "${unit_dir}/.ingestion-shutdown.conf.tmp" ||
       ! "${elevate[@]}" mv -f -- "${unit_dir}/.ingestion-shutdown.conf.tmp" "${unit_dir}/ingestion-shutdown.conf"; then
        rm -f -- "${source_file}"
        "${elevate[@]}" rm -f -- "${unit_dir}/.ingestion-shutdown.conf.tmp"
        return 1
    fi
    rm -f -- "${source_file}"
    $SYSTEMCTL daemon-reload
}

configure_backend_allocator() {
    # Memory allocator switch, off by default. pymalloc keeps freed arenas
    # after a large financial read (one account history in a fresh process
    # leaves 1.6 GB resident with ~170k more live objects; mimalloc leaves
    # 0.5 GB at +30% CPU). A host opts in by writing "mimalloc" to
    # ${BACKEND_ALLOCATOR_SWITCH}; any other content or no file removes the
    # drop-in, so the service runs Python's default allocator. The switch lives
    # outside the checkout so a release or rollback never flips it.
    local elevate=()
    local choice=""
    local source_file
    local unit_dir=/etc/systemd/system/owl-backend-v2.service.d
    local unit="${unit_dir}/backend-allocator.conf"
    local switch="${BACKEND_ALLOCATOR_SWITCH:-/etc/default/owl-backend-allocator}"
    if [ "$(id -u)" -ne 0 ]; then
        elevate=(sudo)
    fi
    if [ -r "${switch}" ]; then
        choice="$(tr -d '[:space:]' < "${switch}")"
    fi
    if [ "${choice}" != "mimalloc" ]; then
        if [ -e "${unit}" ]; then
            "${elevate[@]}" rm -f -- "${unit}" || return 1
            $SYSTEMCTL daemon-reload
        fi
        return 0
    fi
    source_file="$(mktemp)" || return 1
    if ! printf '[Service]\nEnvironment=PYTHONMALLOC=mimalloc\n' > "${source_file}"; then
        rm -f -- "${source_file}"
        return 1
    fi
    if cmp -s "${source_file}" "${unit}"; then
        rm -f -- "${source_file}"
        return 0
    fi
    if ! "${elevate[@]}" install -d -m 0755 "${unit_dir}" ||
       ! "${elevate[@]}" install -m 0644 "${source_file}" "${unit_dir}/.backend-allocator.conf.tmp" ||
       ! "${elevate[@]}" mv -f -- "${unit_dir}/.backend-allocator.conf.tmp" "${unit}"; then
        rm -f -- "${source_file}"
        "${elevate[@]}" rm -f -- "${unit_dir}/.backend-allocator.conf.tmp"
        return 1
    fi
    rm -f -- "${source_file}"
    $SYSTEMCTL daemon-reload
}
