#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Owl Investigation Console - Deploy Script
# Usage: bash deploy/deploy.sh
# Run as user: conor
# ============================================================

# --- Configuration ---
PROJECT_DIR="/home/conor/owl-console/owl-n4j"
VENV_DIR="${PROJECT_DIR}/.venv"
BACKEND_DIR="${PROJECT_DIR}/backend"
FRONTEND_DIR="${PROJECT_DIR}/frontend"
LOG_DIR="${PROJECT_DIR}/deploy/logs"
LOG_FILE="${LOG_DIR}/deploy-$(date +%Y%m%d-%H%M%S).log"
HEALTH_URL="http://127.0.0.1:8000/health"
HEALTH_RETRIES=15
HEALTH_DELAY=2

# --- Colour output ---
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

# --- Log everything ---
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD}  Owl Deploy${NC} - $(date)"
echo -e "${BOLD}============================================${NC}"

# --- Track timing ---
DEPLOY_START=$(date +%s)

# ============================================================
# Step 1: Pre-flight checks
# ============================================================
step "Pre-flight checks"

# Check user
if [ "$(whoami)" != "conor" ]; then
    fail "Must run as user 'conor'. Use: sudo su - conor"
    exit 1
fi
success "Running as user: conor"

# Check disk space (warn if < 2GB free)
AVAIL_KB=$(df -k "$PROJECT_DIR" | tail -1 | awk '{print $4}')
AVAIL_MB=$(( AVAIL_KB / 1024 ))
if [ "$AVAIL_KB" -lt 2097152 ]; then
    warn "Low disk space: ${AVAIL_MB}MB free (recommend 2GB+)"
else
    success "Disk space: ${AVAIL_MB}MB free"
fi

# Check Docker containers
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "owl-n4j"; then
    success "Neo4j container running"
else
    warn "Neo4j container (owl-n4j) not detected - check Docker"
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "owl-pg"; then
    success "PostgreSQL container running"
else
    warn "PostgreSQL container (owl-pg) not detected - check Docker"
fi

# ============================================================
# Step 2: Record current state for rollback
# ============================================================
step "Recording current state"

cd "$PROJECT_DIR"
PREV_COMMIT=$(git rev-parse HEAD)
PREV_COMMIT_SHORT=$(git rev-parse --short HEAD)
echo "$PREV_COMMIT" > "${LOG_DIR}/.last-good-commit"
success "Current commit: ${PREV_COMMIT_SHORT} (saved for rollback)"

# ============================================================
# Step 3: Stash local changes
# ============================================================
step "Checking for local changes"

if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
    warn "Local changes detected - stashing..."
    git stash push -m "deploy-autostash-$(date +%Y%m%d-%H%M%S)"
    success "Changes stashed safely"
else
    success "Working directory clean"
fi

# ============================================================
# Step 4: Pull latest code
# ============================================================
step "Pulling latest from main"

if ! git pull origin main --ff-only; then
    fail "git pull failed (merge conflict or diverged history)"
    fail "Manual intervention required. Run: git status"
    fail "Stashed changes (if any) are safe. Run: git stash list"
    exit 1
fi

NEW_COMMIT=$(git rev-parse HEAD)
NEW_COMMIT_SHORT=$(git rev-parse --short HEAD)

if [ "$PREV_COMMIT" = "$NEW_COMMIT" ]; then
    warn "No new commits pulled. Continuing (may need dep updates)."
else
    COMMIT_COUNT=$(git rev-list --count ${PREV_COMMIT}..${NEW_COMMIT})
    success "Pulled ${COMMIT_COUNT} new commit(s): ${PREV_COMMIT_SHORT} -> ${NEW_COMMIT_SHORT}"
fi

# ============================================================
# Step 5: Install backend dependencies
# ============================================================
step "Installing backend dependencies"

"${VENV_DIR}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" --quiet 2>&1
success "Backend dependencies installed"

# ============================================================
# Step 6: Install frontend dependencies and build
# ============================================================
step "Installing frontend dependencies"

cd "$FRONTEND_DIR"
npm ci --silent 2>&1
success "Frontend dependencies installed"

step "Building frontend for production"

npm run build 2>&1
success "Frontend built -> dist/"
cd "$PROJECT_DIR"

# ============================================================
# Step 7: Run database migrations
# ============================================================
step "Running database migrations"

cd "$BACKEND_DIR"
"${VENV_DIR}/bin/alembic" upgrade head 2>&1
success "Database migrations complete"
cd "$PROJECT_DIR"

# ============================================================
# Step 8: Restart services
# ============================================================
step "Stopping backend service"

# Clean up any legacy screen sessions
screen -XS frontend quit 2>/dev/null || true
screen -XS backend quit 2>/dev/null || true

sudo systemctl stop owl-backend 2>/dev/null || true
success "Backend stopped"

step "Starting backend service"
sudo systemctl start owl-backend
success "Backend started"

step "Reloading Nginx"
sudo systemctl reload nginx
success "Nginx reloaded"

# ============================================================
# Step 9: Health check
# ============================================================
step "Running health check"

HEALTHY=false
for i in $(seq 1 $HEALTH_RETRIES); do
    sleep "$HEALTH_DELAY"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")

    if [ "$HTTP_CODE" = "200" ]; then
        RESPONSE=$(curl -s "$HEALTH_URL" 2>/dev/null)
        success "Health check passed (HTTP 200)"
        echo "  Response: ${RESPONSE}"
        HEALTHY=true
        break
    fi

    echo "  Attempt ${i}/${HEALTH_RETRIES}: HTTP ${HTTP_CODE} - waiting..."
done

if [ "$HEALTHY" = true ]; then
    # ============================================================
    # Success!
    # ============================================================
    DEPLOY_END=$(date +%s)
    DEPLOY_DURATION=$(( DEPLOY_END - DEPLOY_START ))

    echo ""
    echo -e "${GREEN}${BOLD}============================================${NC}"
    echo -e "${GREEN}${BOLD}  Deploy successful!${NC}"
    echo -e "${GREEN}============================================${NC}"
    echo -e "  Commit:   ${NEW_COMMIT_SHORT}"
    echo -e "  Duration: ${DEPLOY_DURATION}s"
    echo -e "  Log:      ${LOG_FILE}"
    echo -e "  Time:     $(date)"
    echo ""
    exit 0
fi

# ============================================================
# Health check failed - ROLLBACK
# ============================================================
echo ""
fail "Health check failed after ${HEALTH_RETRIES} attempts"
fail "ROLLING BACK to commit ${PREV_COMMIT_SHORT}..."
echo ""

cd "$PROJECT_DIR"
git checkout "$PREV_COMMIT" -- .

# Reinstall old deps
step "Rollback: reinstalling backend dependencies"
"${VENV_DIR}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" --quiet 2>&1 || true

step "Rollback: rebuilding frontend"
cd "$FRONTEND_DIR"
npm ci --silent 2>&1 || true
npm run build 2>&1 || true
cd "$PROJECT_DIR"

step "Rollback: restarting services"
sudo systemctl restart owl-backend
sudo systemctl reload nginx

# Check if rollback worked
sleep 3
ROLLBACK_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")

if [ "$ROLLBACK_CODE" = "200" ]; then
    warn "Rollback successful - running on commit ${PREV_COMMIT_SHORT}"
    warn "The failed deploy has been reverted. Check the log for details:"
    warn "  ${LOG_FILE}"
else
    fail "ROLLBACK ALSO FAILED (HTTP ${ROLLBACK_CODE})"
    fail "Manual intervention required!"
    fail "  Log: ${LOG_FILE}"
    fail "  Last good commit: ${PREV_COMMIT}"
fi

exit 1
