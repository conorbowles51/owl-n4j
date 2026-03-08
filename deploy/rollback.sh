#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Owl Investigation Console - Rollback Script
# Usage: bash deploy/rollback.sh [commit-hash]
# If no commit provided, uses the last good commit from deploy logs.
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

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Auto-detect venv directory (.venv or venv)
if [ -d "${PROJECT_DIR}/.venv" ]; then
    VENV_DIR="${PROJECT_DIR}/.venv"
elif [ -d "${PROJECT_DIR}/venv" ]; then
    VENV_DIR="${PROJECT_DIR}/venv"
else
    echo "No venv found at ${PROJECT_DIR}/.venv or ${PROJECT_DIR}/venv"
    exit 1
fi
BACKEND_DIR="${PROJECT_DIR}/backend"
FRONTEND_DIR="${PROJECT_DIR}/frontend"
LOG_DIR="${PROJECT_DIR}/deploy/logs"
HEALTH_URL="http://127.0.0.1:8000/health"

# Detect deploy user - if root, use the project dir owner
if [ "$(id -u)" -eq 0 ]; then
    DEPLOY_USER="$(stat -c '%U' "${PROJECT_DIR}")"
    RUN_AS="sudo -u ${DEPLOY_USER}"
    SYSTEMCTL="systemctl"
else
    DEPLOY_USER="$(whoami)"
    RUN_AS=""
    SYSTEMCTL="sudo systemctl"
fi

# Get target commit
if [ -n "${1:-}" ]; then
    TARGET_COMMIT="$1"
else
    LAST_GOOD_FILE="${LOG_DIR}/.last-good-commit"
    if [ -f "$LAST_GOOD_FILE" ]; then
        TARGET_COMMIT=$(cat "$LAST_GOOD_FILE")
    else
        fail "No commit specified and no .last-good-commit file found."
        fail "Usage: bash deploy/rollback.sh <commit-hash>"
        exit 1
    fi
fi

TARGET_SHORT=$(echo "$TARGET_COMMIT" | cut -c1-7)
CURRENT_SHORT=$(cd "$PROJECT_DIR" && git rev-parse --short HEAD)

echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${YELLOW}${BOLD}  Owl Rollback${NC}"
echo -e "${BOLD}============================================${NC}"
echo -e "  Current: ${CURRENT_SHORT}"
echo -e "  Target:  ${TARGET_SHORT}"
echo ""

read -p "Proceed with rollback? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Rollback cancelled."
    exit 0
fi

# ============================================================
# Rollback
# ============================================================
cd "$PROJECT_DIR"

step "Checking out target commit"
$RUN_AS git checkout "$TARGET_COMMIT" -- .
success "Code reverted to ${TARGET_SHORT}"

step "Reinstalling backend dependencies"
$RUN_AS "${VENV_DIR}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" --quiet 2>&1
success "Backend dependencies installed"

step "Rebuilding frontend"
cd "$FRONTEND_DIR"
$RUN_AS npm ci --silent 2>&1
$RUN_AS npm run build 2>&1
cd "$PROJECT_DIR"
success "Frontend rebuilt"

step "Restarting services"
$SYSTEMCTL restart owl-backend
$SYSTEMCTL reload nginx
success "Services restarted"

step "Health check"
sleep 3
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    success "Health check passed"
    echo ""
    echo -e "${GREEN}${BOLD}  Rollback successful!${NC}"
    echo -e "  Running on commit: ${TARGET_SHORT}"
    echo ""
else
    fail "Health check failed (HTTP ${HTTP_CODE})"
    fail "Manual intervention required"
    exit 1
fi
