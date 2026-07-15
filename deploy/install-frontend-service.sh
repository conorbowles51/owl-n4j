#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"
DEPLOY_USER="$(stat -c '%U' "${PROJECT_DIR}")"
DEPLOY_GROUP="$(stat -c '%G' "${PROJECT_DIR}")"

if [ "$(id -u)" -ne 0 ]; then
    echo "install-frontend-service.sh must run as root" >&2
    exit 1
fi

if [ ! -f "${ENV_FILE}" ]; then
    echo "Missing ${ENV_FILE}" >&2
    exit 1
fi

cat > /etc/systemd/system/owl-frontend-v2.service << SERVICE_EOF
[Unit]
Description=Loupe V2 Frontend (compiled Vite bundle)
After=network.target

[Service]
Type=simple
User=${DEPLOY_USER}
Group=${DEPLOY_GROUP}
WorkingDirectory=${PROJECT_DIR}/frontend_v2
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=${ENV_FILE}
ExecStart=/bin/bash -lc 'exec /usr/bin/npm run preview -- --strictPort --host 0.0.0.0 --port \${FRONTEND_PORT:-5174}'
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=owl-frontend-v2

[Install]
WantedBy=multi-user.target
SERVICE_EOF

systemctl daemon-reload
