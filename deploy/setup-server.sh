#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

step()    { echo -e "\n${BLUE}[STEP]${NC} ${BOLD}$1${NC}"; }
success() { echo -e "  ${GREEN}[  OK]${NC} $1"; }
warn()    { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
fail()    { echo -e "  ${RED}[FAIL]${NC} $1"; }

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"
DEPLOY_USER="$(stat -c '%U' "${PROJECT_DIR}")"
DEPLOY_GROUP="$(stat -c '%G' "${PROJECT_DIR}")"

if [ -d "${PROJECT_DIR}/.venv" ]; then
    VENV_DIR="${PROJECT_DIR}/.venv"
elif [ -d "${PROJECT_DIR}/venv" ]; then
    VENV_DIR="${PROJECT_DIR}/venv"
else
    fail "No venv found at ${PROJECT_DIR}/.venv or ${PROJECT_DIR}/venv"
    exit 1
fi

if [ ! -f "${ENV_FILE}" ]; then
    fail "Missing ${ENV_FILE}. Copy .env.example to .env and fill it in first."
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

API_PORT="${API_PORT:-8002}"
FRONTEND_PORT="${FRONTEND_PORT:-5174}"
HEALTH_URL="http://127.0.0.1:${API_PORT}/health"

echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD}  Owl V2 Server Setup${NC}"
echo -e "${BOLD}============================================${NC}"
echo -e "  Project dir: ${PROJECT_DIR}"
echo -e "  Env file:    ${ENV_FILE}"
echo -e "  API port:    ${API_PORT}"
echo -e "  Frontend:    ${FRONTEND_PORT}"

if [ "$(id -u)" -ne 0 ]; then
    fail "Must run as root. Use: sudo bash deploy/setup-server.sh"
    exit 1
fi

step "Installing systemd services"

cat > /etc/systemd/system/owl-backend-v2.service << SERVICE_EOF
[Unit]
Description=Owl V2 Backend (FastAPI/Uvicorn)
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=${DEPLOY_USER}
Group=${DEPLOY_GROUP}
WorkingDirectory=${PROJECT_DIR}/backend
Environment="PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=${ENV_FILE}
ExecStart=/bin/bash -lc 'exec ${VENV_DIR}/bin/uvicorn main:app --host 0.0.0.0 --port \${API_PORT:-8002} --workers 2'
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=owl-backend-v2

[Install]
WantedBy=multi-user.target
SERVICE_EOF
success "Installed owl-backend-v2.service"

cat > /etc/systemd/system/owl-frontend-v2.service << SERVICE_EOF
[Unit]
Description=Owl V2 Frontend (Vite Dev Server)
After=network.target

[Service]
Type=simple
User=${DEPLOY_USER}
Group=${DEPLOY_GROUP}
WorkingDirectory=${PROJECT_DIR}/frontend_v2
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=${ENV_FILE}
ExecStart=/bin/bash -lc 'exec /usr/bin/npm run dev -- --host 0.0.0.0 --port \${FRONTEND_PORT:-5174}'
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=owl-frontend-v2

[Install]
WantedBy=multi-user.target
SERVICE_EOF
success "Installed owl-frontend-v2.service"

systemctl daemon-reload
systemctl enable owl-backend-v2
systemctl enable owl-frontend-v2
success "Enabled owl-backend-v2 and owl-frontend-v2"

step "Configuring sudo permissions"

cat > /etc/sudoers.d/owl-v2-deploy << SUDO_EOF
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl start owl-backend-v2
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl stop owl-backend-v2
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart owl-backend-v2
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl status owl-backend-v2
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl start owl-frontend-v2
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl stop owl-frontend-v2
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart owl-frontend-v2
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl status owl-frontend-v2
SUDO_EOF

chmod 440 /etc/sudoers.d/owl-v2-deploy

if visudo -c -f /etc/sudoers.d/owl-v2-deploy >/dev/null 2>&1; then
    success "Configured sudo permissions for ${DEPLOY_USER}"
else
    fail "Invalid sudoers file"
    rm -f /etc/sudoers.d/owl-v2-deploy
    exit 1
fi

step "Installing dependencies"

mkdir -p "${PROJECT_DIR}/deploy/logs"
chown "${DEPLOY_USER}:${DEPLOY_GROUP}" "${PROJECT_DIR}/deploy/logs"

sudo -u "${DEPLOY_USER}" "${VENV_DIR}/bin/pip" install -r "${PROJECT_DIR}/backend/requirements.txt" --quiet
success "Backend dependencies installed"

cd "${PROJECT_DIR}/frontend_v2"
sudo -u "${DEPLOY_USER}" npm ci --silent
success "Frontend V2 dependencies installed"

step "Starting Docker stack"
cd "${PROJECT_DIR}"
docker compose up -d --build
success "Docker stack started"

step "Starting services"
systemctl restart owl-backend-v2
systemctl restart owl-frontend-v2
success "V2 services restarted"

step "Health check"
sleep 10
RESPONSE="$(curl -fsS "${HEALTH_URL}" 2>/dev/null || true)"
if echo "${RESPONSE}" | grep -q '"status":"ok"' && ! echo "${RESPONSE}" | grep -Eq '"neo4j":"error:|"evidence_engine":"(error:|unavailable)"'; then
    success "Health check passed"
else
    warn "Health check did not fully pass yet"
    echo "  Response: ${RESPONSE:-<no response>}"
fi

echo ""
echo -e "${GREEN}${BOLD}============================================${NC}"
echo -e "${GREEN}${BOLD}  Owl V2 setup complete${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Frontend: http://<server-ip>:${FRONTEND_PORT}"
echo "  API:      http://<server-ip>:${API_PORT}"
echo "  Services: systemctl status owl-backend-v2 / owl-frontend-v2"
echo "  Logs:     journalctl -u owl-backend-v2 -f"
echo "            journalctl -u owl-frontend-v2 -f"
