#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"
BACKEND_DIR="${PROJECT_DIR}/backend"
FRONTEND_DIR="${PROJECT_DIR}/frontend_v2"
LOG_DIR="${PROJECT_DIR}/deploy/logs"

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

if [ -d "${PROJECT_DIR}/.venv" ]; then
    VENV_DIR="${PROJECT_DIR}/.venv"
elif [ -d "${PROJECT_DIR}/venv" ]; then
    VENV_DIR="${PROJECT_DIR}/venv"
else
    fail "No venv found at ${PROJECT_DIR}/.venv or ${PROJECT_DIR}/venv"
    exit 1
fi

if [ ! -f "${ENV_FILE}" ]; then
    fail "Missing ${ENV_FILE}"
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

API_PORT="${API_PORT:-8002}"
HEALTH_URL="http://127.0.0.1:${API_PORT}/health"

if [ "$(id -u)" -eq 0 ]; then
    DEPLOY_USER="$(stat -c '%U' "${PROJECT_DIR}")"
    RUN_AS="sudo -u ${DEPLOY_USER}"
    SYSTEMCTL="systemctl"
else
    DEPLOY_USER="$(whoami)"
    RUN_AS=""
    SYSTEMCTL="sudo systemctl"
fi

if [ -n "${1:-}" ]; then
    TARGET_COMMIT="$1"
else
    LAST_GOOD_FILE="${LOG_DIR}/.last-good-commit"
    if [ -f "${LAST_GOOD_FILE}" ]; then
        TARGET_COMMIT="$(cat "${LAST_GOOD_FILE}")"
    else
        fail "No commit specified and no rollback marker found"
        exit 1
    fi
fi

TARGET_SHORT="$(echo "${TARGET_COMMIT}" | cut -c1-7)"
CURRENT_SHORT="$(cd "${PROJECT_DIR}" && git rev-parse --short HEAD)"

echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${YELLOW}${BOLD}  Owl V2 Rollback${NC}"
echo -e "${BOLD}============================================${NC}"
echo -e "  Current: ${CURRENT_SHORT}"
echo -e "  Target:  ${TARGET_SHORT}"

read -r -p "Proceed with rollback? [y/N] " REPLY
if [[ ! "${REPLY}" =~ ^[Yy]$ ]]; then
    echo "Rollback cancelled."
    exit 0
fi

cd "${PROJECT_DIR}"

step "Checking out target commit"
$RUN_AS git checkout "${TARGET_COMMIT}" -- .
success "Code reverted to ${TARGET_SHORT}"

step "Reinstalling dependencies"
$RUN_AS "${VENV_DIR}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" --quiet
cd "${FRONTEND_DIR}"
$RUN_AS npm ci --silent
cd "${PROJECT_DIR}"
success "Dependencies installed"

step "Rebuilding Docker stack"
docker compose up -d --build
success "Docker stack refreshed"

step "Restarting services"
$SYSTEMCTL restart owl-backend-v2
$SYSTEMCTL restart owl-frontend-v2
success "V2 services restarted"

step "Health check"
sleep 10
RESPONSE="$(curl -fsS --max-time 5 "${HEALTH_URL}" 2>/dev/null || true)"
if echo "${RESPONSE}" | grep -q '"status":"ok"' && ! echo "${RESPONSE}" | grep -Eq '"neo4j":"error:|"evidence_engine":"(error:|unavailable)"'; then
    success "Health check passed"
    echo ""
    echo -e "${GREEN}${BOLD}  Rollback successful${NC}"
    echo -e "  Running on commit: ${TARGET_SHORT}"
else
    fail "Health check failed after rollback"
    fail "Response: ${RESPONSE:-<no response>}"
    exit 1
fi
