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

PROJECT_DIR="/home/conor/owl-console/owl-n4j"

echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD}  Owl Server Setup${NC}"
echo -e "${BOLD}============================================${NC}"

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
# Step 2: Configure Nginx
# ============================================================
step "Configuring Nginx"

# Remove default site
rm -f /etc/nginx/sites-enabled/default
success "Removed default Nginx site"

# Symlink Owl config
ln -sf "${PROJECT_DIR}/deploy/owl-nginx.conf" /etc/nginx/sites-enabled/owl.conf
success "Linked Owl Nginx config"

# Test config
if nginx -t 2>&1; then
    success "Nginx config valid"
else
    fail "Nginx config invalid - check deploy/owl-nginx.conf"
    exit 1
fi

# ============================================================
# Step 3: Install systemd service
# ============================================================
step "Installing systemd service"

cp "${PROJECT_DIR}/deploy/owl-backend.service" /etc/systemd/system/owl-backend.service
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

cat > /etc/sudoers.d/owl-deploy << 'EOF'
# Allow conor to manage Owl services without password (for deploy script)
conor ALL=(ALL) NOPASSWD: /bin/systemctl start owl-backend
conor ALL=(ALL) NOPASSWD: /bin/systemctl stop owl-backend
conor ALL=(ALL) NOPASSWD: /bin/systemctl restart owl-backend
conor ALL=(ALL) NOPASSWD: /bin/systemctl reload nginx
conor ALL=(ALL) NOPASSWD: /bin/systemctl status owl-backend
conor ALL=(ALL) NOPASSWD: /bin/systemctl status nginx
EOF

chmod 440 /etc/sudoers.d/owl-deploy

# Validate sudoers file
if visudo -c -f /etc/sudoers.d/owl-deploy 2>&1; then
    success "Sudo permissions configured"
else
    fail "Sudoers file invalid - removing"
    rm -f /etc/sudoers.d/owl-deploy
    exit 1
fi

# ============================================================
# Step 5: Kill existing screen sessions
# ============================================================
step "Cleaning up legacy screen sessions"

sudo -u conor screen -XS frontend quit 2>/dev/null && success "Killed frontend screen" || success "No frontend screen found"
sudo -u conor screen -XS backend quit 2>/dev/null && success "Killed backend screen" || success "No backend screen found"

# ============================================================
# Step 6: Create directories
# ============================================================
step "Creating directories"

mkdir -p "${PROJECT_DIR}/deploy/logs"
chown conor:conor "${PROJECT_DIR}/deploy/logs"
success "Deploy log directory created"

# ============================================================
# Step 7: Build frontend (initial production build)
# ============================================================
step "Building frontend for production"

cd "${PROJECT_DIR}/frontend"
sudo -u conor npm ci --silent 2>&1
sudo -u conor npm run build 2>&1
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
echo "    2. Future deploys: sudo su - conor && bash deploy/deploy.sh"
echo ""
