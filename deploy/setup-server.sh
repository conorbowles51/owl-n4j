#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Owl Investigation Console - One-Time Server Setup
# Usage: sudo bash deploy/setup-server.sh
# Run as: root
#
# Sets up systemd services for backend + frontend.
# No nginx — just uvicorn on :8000 and vite on :5173,
# exactly like the old screen session setup but with
# auto-restart and proper logging.
# ============================================================

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

# Auto-detect project directory from script location
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Auto-detect the deploy user (owner of the project directory)
DEPLOY_USER="$(stat -c '%U' "${PROJECT_DIR}")"
DEPLOY_GROUP="$(stat -c '%G' "${PROJECT_DIR}")"

# Auto-detect venv directory (.venv or venv)
if [ -d "${PROJECT_DIR}/.venv" ]; then
    VENV_DIR="${PROJECT_DIR}/.venv"
elif [ -d "${PROJECT_DIR}/venv" ]; then
    VENV_DIR="${PROJECT_DIR}/venv"
else
    echo "  No venv found at ${PROJECT_DIR}/.venv or ${PROJECT_DIR}/venv"
    exit 1
fi

echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD}  Owl Server Setup${NC}"
echo -e "${BOLD}============================================${NC}"
echo -e "  Project dir:  ${PROJECT_DIR}"
echo -e "  Deploy user:  ${DEPLOY_USER}"
echo -e "  Venv:         ${VENV_DIR}"

# Check running as root
if [ "$(id -u)" -ne 0 ]; then
    fail "Must run as root. Use: sudo bash deploy/setup-server.sh"
    exit 1
fi

# ============================================================
# Step 1: Stop and disable nginx (if running)
# ============================================================
step "Cleaning up nginx (not needed)"

if systemctl is-active nginx &>/dev/null; then
    systemctl stop nginx
    success "Stopped nginx"
fi
if systemctl is-enabled nginx &>/dev/null; then
    systemctl disable nginx
    success "Disabled nginx auto-start"
fi

# ============================================================
# Step 2: Install systemd services
# ============================================================
step "Installing systemd services"

# Backend service - uvicorn on 0.0.0.0:8000 (same as old screen session)
cat > /etc/systemd/system/owl-backend.service << SERVICE_EOF
[Unit]
Description=Owl Investigation Console - Backend (FastAPI/Uvicorn)
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=${DEPLOY_USER}
Group=${DEPLOY_GROUP}
WorkingDirectory=${PROJECT_DIR}/backend
Environment="PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=${PROJECT_DIR}/.env
ExecStart=${VENV_DIR}/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=owl-backend

[Install]
WantedBy=multi-user.target
SERVICE_EOF
success "Backend service installed (uvicorn on :8000)"

# Frontend service - vite dev server on 0.0.0.0:5173 (same as old screen session)
cat > /etc/systemd/system/owl-frontend.service << SERVICE_EOF
[Unit]
Description=Owl Investigation Console - Frontend (Vite Dev Server)
After=network.target

[Service]
Type=simple
User=${DEPLOY_USER}
Group=${DEPLOY_GROUP}
WorkingDirectory=${PROJECT_DIR}/frontend
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
ExecStart=/usr/bin/npx vite --host 0.0.0.0
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=owl-frontend

[Install]
WantedBy=multi-user.target
SERVICE_EOF
success "Frontend service installed (vite on :5173)"

systemctl daemon-reload

# Enable auto-start on boot
systemctl enable owl-backend
systemctl enable owl-frontend
success "Services enabled for auto-start on boot"

# ============================================================
# Step 3: Configure sudo permissions for deploy user
# ============================================================
step "Configuring sudo permissions"

cat > /etc/sudoers.d/owl-deploy << SUDO_EOF
# Allow ${DEPLOY_USER} to manage Owl services without password
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl start owl-backend
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl stop owl-backend
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart owl-backend
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl status owl-backend
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl start owl-frontend
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl stop owl-frontend
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart owl-frontend
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl status owl-frontend
SUDO_EOF

chmod 440 /etc/sudoers.d/owl-deploy

if visudo -c -f /etc/sudoers.d/owl-deploy 2>&1; then
    success "Sudo permissions configured for ${DEPLOY_USER}"
else
    fail "Sudoers file invalid - removing"
    rm -f /etc/sudoers.d/owl-deploy
    exit 1
fi

# ============================================================
# Step 4: Kill existing screen sessions
# ============================================================
step "Cleaning up legacy screen sessions"

sudo -u "${DEPLOY_USER}" screen -XS frontend quit 2>/dev/null && success "Killed frontend screen" || success "No frontend screen found"
sudo -u "${DEPLOY_USER}" screen -XS backend quit 2>/dev/null && success "Killed backend screen" || success "No backend screen found"

# ============================================================
# Step 5: Create directories & install frontend deps
# ============================================================
step "Setup"

mkdir -p "${PROJECT_DIR}/deploy/logs"
chown "${DEPLOY_USER}:${DEPLOY_GROUP}" "${PROJECT_DIR}/deploy/logs"
success "Deploy log directory created"

cd "${PROJECT_DIR}/frontend"
sudo -u "${DEPLOY_USER}" npm ci --silent 2>&1
success "Frontend dependencies installed"

# ============================================================
# Step 6: Start services
# ============================================================
step "Starting services"

systemctl restart owl-backend
success "Backend started (port 8000)"

systemctl restart owl-frontend
success "Frontend started (port 5173)"

# Quick health check (backend needs time to load snapshots)
sleep 10
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/health" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    success "Health check passed"
else
    warn "Backend not yet responding (HTTP ${HTTP_CODE}) - may need a moment to start"
fi

# ============================================================
# Done
# ============================================================
echo ""
echo -e "${GREEN}${BOLD}============================================${NC}"
echo -e "${GREEN}${BOLD}  Server setup complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Access:"
echo "    Frontend: http://<server-ip>:5173"
echo "    API:      http://<server-ip>:8000"
echo ""
echo "  Services:"
echo "    Backend:  systemctl status owl-backend"
echo "    Frontend: systemctl status owl-frontend"
echo ""
echo "  Logs:"
echo "    Backend:  journalctl -u owl-backend -f"
echo "    Frontend: journalctl -u owl-frontend -f"
echo "    Deploy:   ls ${PROJECT_DIR}/deploy/logs/"
echo ""
echo "  Next steps:"
echo "    1. Verify the app at http://<server-ip>:5173"
echo "    2. Future deploys: bash ${PROJECT_DIR}/deploy/deploy.sh"
echo ""
