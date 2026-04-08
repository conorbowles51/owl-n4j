#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"
BACKEND_DIR="${PROJECT_DIR}/backend"
FRONTEND_DIR="${PROJECT_DIR}/frontend_v2"
LOG_DIR="${PROJECT_DIR}/deploy/logs"
LOG_FILE="${LOG_DIR}/deploy-$(date +%Y%m%d-%H%M%S).log"

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
    fail "Missing ${ENV_FILE}. Copy .env.example to .env and fill it in first."
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

API_PORT="${API_PORT:-8002}"
HEALTH_URL="http://127.0.0.1:${API_PORT}/health"
HEALTH_RETRIES=20
HEALTH_DELAY=3

mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD}  Owl V2 Deploy${NC} - $(date)"
echo -e "${BOLD}============================================${NC}"

DEPLOY_START=$(date +%s)

if [ "$(id -u)" -eq 0 ]; then
    DEPLOY_USER="$(stat -c '%U' "${PROJECT_DIR}")"
    RUN_AS="sudo -u ${DEPLOY_USER}"
    SYSTEMCTL="systemctl"
    success "Running as root (app commands as ${DEPLOY_USER})"
else
    DEPLOY_USER="$(whoami)"
    RUN_AS=""
    SYSTEMCTL="sudo systemctl"
    success "Running as user ${DEPLOY_USER}"
fi

step "Pre-flight checks"

AVAIL_KB=$(df -k "${PROJECT_DIR}" | tail -1 | awk '{print $4}')
AVAIL_MB=$(( AVAIL_KB / 1024 ))
if [ "${AVAIL_KB}" -lt 2097152 ]; then
    warn "Low disk space: ${AVAIL_MB}MB free"
else
    success "Disk space: ${AVAIL_MB}MB free"
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "owl-v2-n4j"; then
    success "V2 Neo4j container detected"
else
    warn "V2 Neo4j container not running yet"
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "owl-v2-pg"; then
    success "V2 PostgreSQL container detected"
else
    warn "V2 PostgreSQL container not running yet"
fi

step "Recording current state"

cd "${PROJECT_DIR}"
PREV_COMMIT="$(git rev-parse HEAD)"
PREV_COMMIT_SHORT="$(git rev-parse --short HEAD)"
CURRENT_BRANCH="${DEPLOY_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"

if [ -z "${CURRENT_BRANCH}" ] || [ "${CURRENT_BRANCH}" = "HEAD" ]; then
    fail "Unable to determine deploy branch. Check out a branch or set DEPLOY_BRANCH in ${ENV_FILE}."
    exit 1
fi

echo "${PREV_COMMIT}" > "${LOG_DIR}/.last-good-commit"
success "Saved rollback commit ${PREV_COMMIT_SHORT} on branch ${CURRENT_BRANCH}"

step "Checking for local changes"

if ! $RUN_AS git diff --quiet 2>/dev/null || ! $RUN_AS git diff --cached --quiet 2>/dev/null; then
    warn "Local changes detected - stashing"
    $RUN_AS git stash push -m "deploy-autostash-$(date +%Y%m%d-%H%M%S)"
    success "Changes stashed"
else
    success "Working directory clean"
fi

step "Pulling latest from ${CURRENT_BRANCH}"

if ! git pull origin "${CURRENT_BRANCH}" --ff-only; then
    fail "git pull failed"
    exit 1
fi

NEW_COMMIT="$(git rev-parse HEAD)"
NEW_COMMIT_SHORT="$(git rev-parse --short HEAD)"
if [ "${PREV_COMMIT}" = "${NEW_COMMIT}" ]; then
    warn "No new commits pulled"
else
    success "Updated ${PREV_COMMIT_SHORT} -> ${NEW_COMMIT_SHORT}"
fi

step "Installing backend dependencies"
$RUN_AS "${VENV_DIR}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" --quiet
success "Backend dependencies installed"

step "Installing frontend dependencies"
cd "${FRONTEND_DIR}"
$RUN_AS npm ci --silent
success "Frontend V2 dependencies installed"
cd "${PROJECT_DIR}"

step "Refreshing Docker stack"
docker compose up -d --build
success "Docker stack refreshed"

step "Running database migrations"
cd "${BACKEND_DIR}"
$RUN_AS "${VENV_DIR}/bin/alembic" upgrade head
success "Database migrations complete"
cd "${PROJECT_DIR}"

step "Restarting services"
$SYSTEMCTL restart owl-backend-v2
$SYSTEMCTL restart owl-frontend-v2
success "V2 services restarted"

step "Running health check"
echo "  Waiting 10s for backend initialization..."
sleep 10

HEALTHY=false
for i in $(seq 1 ${HEALTH_RETRIES}); do
    sleep "${HEALTH_DELAY}"
    RESPONSE="$(curl -fsS --max-time 5 "${HEALTH_URL}" 2>/dev/null || true)"
    if echo "${RESPONSE}" | grep -q '"status":"ok"' && ! echo "${RESPONSE}" | grep -Eq '"neo4j":"error:|"evidence_engine":"(error:|unavailable)"'; then
        success "Health check passed"
        echo "  Response: ${RESPONSE}"
        HEALTHY=true
        break
    fi
    echo "  Attempt ${i}/${HEALTH_RETRIES}: ${RESPONSE:-<no response>} - waiting..."
done

if [ "${HEALTHY}" = true ]; then
    DEPLOY_END=$(date +%s)
    DEPLOY_DURATION=$(( DEPLOY_END - DEPLOY_START ))
    echo ""
    echo -e "${GREEN}${BOLD}============================================${NC}"
    echo -e "${GREEN}${BOLD}  Deploy successful${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo -e "  Commit:   ${NEW_COMMIT_SHORT}"
    echo -e "  Duration: ${DEPLOY_DURATION}s"
    echo -e "  Log:      ${LOG_FILE}"
    exit 0
fi

echo ""
fail "Health check failed - rolling back to ${PREV_COMMIT_SHORT}"

cd "${PROJECT_DIR}"
$RUN_AS git reset --hard "${PREV_COMMIT}"

step "Rollback: reinstalling dependencies"
$RUN_AS "${VENV_DIR}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" --quiet || true
cd "${FRONTEND_DIR}"
$RUN_AS npm ci --silent || true
cd "${PROJECT_DIR}"

step "Rollback: rebuilding Docker stack"
docker compose up -d --build || true

step "Rollback: restarting services"
$SYSTEMCTL restart owl-backend-v2 || true
$SYSTEMCTL restart owl-frontend-v2 || true

sleep 15
RESPONSE="$(curl -fsS --max-time 5 "${HEALTH_URL}" 2>/dev/null || true)"
if echo "${RESPONSE}" | grep -q '"status":"ok"' && ! echo "${RESPONSE}" | grep -Eq '"neo4j":"error:|"evidence_engine":"(error:|unavailable)"'; then
    warn "Rollback successful - running ${PREV_COMMIT_SHORT}"
    warn "See log: ${LOG_FILE}"
else
    fail "Rollback also failed"
    fail "Log: ${LOG_FILE}"
fi

exit 1
