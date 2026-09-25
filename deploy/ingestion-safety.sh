#!/usr/bin/env bash
# Sourced before checkout changes. Keep the verified gate/function definitions
# in this shell so a rollback to older code cannot weaken its own safety checks.
INGESTION_GATE_CODE="$(cat "${PROJECT_DIR}/deploy/check_ingestion_idle.py")"

check_ingestion_idle() {
    $RUN_AS "${VENV_DIR}/bin/python" -c "${INGESTION_GATE_CODE}" "${BACKEND_DIR}"
}

configure_ingestion_shutdown() {
    local elevate=()
    if [ "$(id -u)" -ne 0 ]; then
        elevate=(sudo)
    fi
    # Uvicorn awaits requests and the application's shielded financial units.
    # Match the engine worker grace window rather than letting systemd's host
    # default terminate them first. This changes no running service or job.
    "${elevate[@]}" install -D -m 0644 /dev/stdin \
        /etc/systemd/system/owl-backend-v2.service.d/ingestion-shutdown.conf <<'UNIT'
[Service]
TimeoutStopSec=14500
UNIT
    $SYSTEMCTL daemon-reload
}
