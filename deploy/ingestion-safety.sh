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
    # Uvicorn awaits requests and the application's shielded financial units.
    # Match the engine worker grace window rather than letting systemd's host
    # default terminate them first. This changes no running service or job.
    # Service runners need not provide /dev/stdin. A regular temporary source
    # also survives privilege elevation without reopening a process fd.
    source_file="$(mktemp)" || return 1
    if ! cat > "${source_file}" <<'UNIT'
[Service]
TimeoutStopSec=14500
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
