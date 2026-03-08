#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Owl Investigation Console - One-Time Server Setup
# Usage: sudo bash deploy/setup-server.sh
# Run as: root
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

echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD}  Owl Server Setup${NC}"
echo -e "${BOLD}============================================${NC}"
echo -e "  Project dir:  ${PROJECT_DIR}"
echo -e "  Deploy user:  ${DEPLOY_USER}"

# Check running as root
if [ "$(id -u)" -ne 0 ]; then
    fail "Must run as root. Use: sudo bash deploy/setup-server.sh"
    exit 1
fi

# ============================================================
# Step 1: Install Nginx
# ============================================================
step "Installing Nginx"

if command -v nginx &>/dev/null; then
    success "Nginx already installed ($(nginx -v 2>&1 | awk -F/ '{print $2}'))"
else
    apt-get update -qq
    apt-get install -y -qq nginx
    success "Nginx installed"
fi

# ============================================================
# Step 2: Generate and install Nginx config
# ============================================================
step "Configuring Nginx"

# Determine Nginx config directory (sites-enabled or conf.d)
if [ -d /etc/nginx/sites-enabled ]; then
    NGINX_CONF_DIR="/etc/nginx/sites-enabled"
elif [ -d /etc/nginx/conf.d ]; then
    NGINX_CONF_DIR="/etc/nginx/conf.d"
else
    NGINX_CONF_DIR="/etc/nginx/conf.d"
    mkdir -p "$NGINX_CONF_DIR"
fi
success "Using Nginx config dir: ${NGINX_CONF_DIR}"

# Ensure nginx.conf includes our config directory
if ! grep -q "$(basename "$NGINX_CONF_DIR")" /etc/nginx/nginx.conf; then
    sed -i "/http {/a \\    include ${NGINX_CONF_DIR}/*.conf;" /etc/nginx/nginx.conf
    success "Added include directive to nginx.conf"
fi

# Remove default sites and any stale owl config (broken symlinks etc)
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
rm -f /etc/nginx/conf.d/default.conf 2>/dev/null || true
rm -f "${NGINX_CONF_DIR}/owl.conf" 2>/dev/null || true
success "Cleaned old Nginx configs"

# Generate Nginx config with correct paths
cat > "${NGINX_CONF_DIR}/owl.conf" << NGINX_EOF
server {
    listen 80;
    server_name _;

    # Frontend - serve production build
    root ${PROJECT_DIR}/frontend/dist;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript;
    gzip_min_length 1000;

    # Static asset caching (Vite uses content-hashed filenames)
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # API proxy to backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # SSE support (streaming entity resolution, chat responses)
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;

        # Long timeouts for LLM operations (chat can take minutes)
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;

        # Large body for evidence uploads
        client_max_body_size 500M;
    }

    # Health check proxy
    location /health {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
    }

    # SPA fallback - all other routes serve index.html for client-side routing
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX_EOF
success "Generated Nginx config at ${NGINX_CONF_DIR}/owl.conf"

# Test config
if nginx -t 2>&1; then
    success "Nginx config valid"
else
    fail "Nginx config invalid"
    exit 1
fi

# ============================================================
# Step 3: Generate and install systemd service
# ============================================================
step "Installing systemd service"

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
Environment="PATH=${PROJECT_DIR}/.venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=${PROJECT_DIR}/.env
ExecStart=${PROJECT_DIR}/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=owl-backend

[Install]
WantedBy=multi-user.target
SERVICE_EOF

systemctl daemon-reload
success "systemd service installed"

# Enable auto-start on boot
systemctl enable owl-backend
systemctl enable nginx
success "Services enabled for auto-start on boot"

# ============================================================
# Step 4: Configure sudo permissions for deploy user
# ============================================================
step "Configuring sudo permissions"

cat > /etc/sudoers.d/owl-deploy << SUDO_EOF
# Allow ${DEPLOY_USER} to manage Owl services without password (for deploy script)
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl start owl-backend
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl stop owl-backend
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart owl-backend
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl reload nginx
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl status owl-backend
${DEPLOY_USER} ALL=(ALL) NOPASSWD: /bin/systemctl status nginx
SUDO_EOF

chmod 440 /etc/sudoers.d/owl-deploy

# Validate sudoers file
if visudo -c -f /etc/sudoers.d/owl-deploy 2>&1; then
    success "Sudo permissions configured for ${DEPLOY_USER}"
else
    fail "Sudoers file invalid - removing"
    rm -f /etc/sudoers.d/owl-deploy
    exit 1
fi

# ============================================================
# Step 5: Kill existing screen sessions
# ============================================================
step "Cleaning up legacy screen sessions"

sudo -u "${DEPLOY_USER}" screen -XS frontend quit 2>/dev/null && success "Killed frontend screen" || success "No frontend screen found"
sudo -u "${DEPLOY_USER}" screen -XS backend quit 2>/dev/null && success "Killed backend screen" || success "No backend screen found"

# ============================================================
# Step 6: Create directories
# ============================================================
step "Creating directories"

mkdir -p "${PROJECT_DIR}/deploy/logs"
chown "${DEPLOY_USER}:${DEPLOY_GROUP}" "${PROJECT_DIR}/deploy/logs"
success "Deploy log directory created"

# ============================================================
# Step 7: Build frontend (initial production build)
# ============================================================
step "Building frontend for production"

cd "${PROJECT_DIR}/frontend"
sudo -u "${DEPLOY_USER}" npm ci --silent 2>&1
sudo -u "${DEPLOY_USER}" npm run build 2>&1
success "Frontend built -> dist/"

# ============================================================
# Step 8: Start services
# ============================================================
step "Starting services"

systemctl start nginx
success "Nginx started"

systemctl start owl-backend
success "Backend started"

# Quick health check
sleep 3
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
echo "  Services:"
echo "    Backend:  systemctl status owl-backend"
echo "    Nginx:    systemctl status nginx"
echo ""
echo "  Logs:"
echo "    Backend:  journalctl -u owl-backend -f"
echo "    Nginx:    journalctl -u nginx -f"
echo "    Deploy:   ls ${PROJECT_DIR}/deploy/logs/"
echo ""
echo "  Next steps:"
echo "    1. Verify the app at http://<server-ip>"
echo "    2. Future deploys: bash ${PROJECT_DIR}/deploy/deploy.sh"
echo ""
