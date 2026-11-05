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

step()    { echo -e "\n${BLUE}[STEP]${NC} $(date -u +%T) ${BOLD}$1${NC}"; }
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
FRONTEND_PORT="${FRONTEND_PORT:-5174}"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}/"
HEALTH_RETRIES=30
HEALTH_DELAY=5

is_compiled_frontend() {
    local html="$1"
    echo "${html}" | grep -Eq 'src="/assets/[^" ]+\.js"' &&
        ! echo "${html}" | grep -Eq '/@vite/client|/src/main\.(js|jsx|ts|tsx)'
}

# The release health check: backend ok with its graph and engine reachable, the
# compiled frontend served, both units active. Sets RESPONSE/FRONTEND_RESPONSE.
release_is_healthy() {
    RESPONSE="$(curl -fsS --max-time 5 "${HEALTH_URL}" 2>/dev/null || true)"
    FRONTEND_RESPONSE="$(curl -fsS --max-time 5 "${FRONTEND_URL}" 2>/dev/null || true)"
    echo "${RESPONSE}" | grep -q '"status":"ok"' &&
        ! echo "${RESPONSE}" | grep -Eq '"neo4j":"error:|"evidence_engine":"(error:|unavailable)"' &&
        is_compiled_frontend "${FRONTEND_RESPONSE}" &&
        $SYSTEMCTL is-active --quiet owl-backend-v2 &&
        frontend_server_active
}

mkdir -p "${LOG_DIR}"

# Running work (imports, engine jobs, uploads) is paused only for the phase that replaces services (lx-releasehold; 5 Nov:
# 7 h of 9 h 19 held for a whole release). This host's script, named in .release-work-hook outside the repo, does it:
# "<hook> pause" right before the first step that needs the work idle, "<hook> resume" as soon as the release is healthy
# or has ended. No file: whoever runs this script pauses before it, and every gate applies from the start.
RELEASE_WORK_HOOK="$(cat "${LOG_DIR}/.release-work-hook" 2>/dev/null || true)"
[ -x "${RELEASE_WORK_HOOK}" ] || RELEASE_WORK_HOOK=""
RELEASE_WORK_PAUSED=false
# Where a job started it, a release runs in the jobs' memory limit: on 5 Nov 13:35 that stalled it 84 minutes with the
# work paused. It takes a scope of its own; its builds still go to the jobs' low-priority slice.
if [ -n "${RELEASE_WORK_HOOK}" ] && [ -z "${LOUPE_RELEASE_SCOPED:-}" ] && [ "$(id -u)" -eq 0 ]; then
    export LOUPE_RELEASE_SCOPED=1
    if systemd-run --scope --quiet --collect true >/dev/null 2>&1; then
        exec systemd-run --scope --quiet --collect bash "${BASH_SOURCE[0]}" "$@"
    fi
fi

# Single-instance guard: an auto-deploy racing a manual build in the same tree
# corrupts npm state mid-install (2026-07-19: tsc saw a half-populated
# typescript package and the deploy failed rc=2).
LOCK_FILE="${LOG_DIR}/.deploy.lock"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
    echo "Another deploy holds ${LOCK_FILE} - waiting up to 10 minutes..."
    if ! flock -w 600 9; then
        echo "FAIL: could not acquire deploy lock after 10 minutes"
        exit 1
    fi
fi

# fd 8 keeps the terminal/runner output so the exit summary can be written
# even when the tee below has been killed with the deploy's process group.
exec 8>&1
exec > >(tee -a "${LOG_FILE}") 2>&1
TEE_PID=$!
DEPLOY_OUTCOME="failed before completion (see the last [FAIL] above)"

echo ""
echo -e "${BOLD}============================================${NC}"
echo -e "${BOLD}  Owl V2 Deploy${NC} - $(date)"
echo -e "${BOLD}============================================${NC}"

DEPLOY_START=$(date +%s)

if [ "$(id -u)" -eq 0 ]; then
    DEPLOY_USER="$(stat -c '%U' "${PROJECT_DIR}")"
    # -H: npm must use the deploy user's HOME/cache, never /root/.npm
    RUN_AS="sudo -u ${DEPLOY_USER} -H"
    SYSTEMCTL="systemctl"
    success "Running as root (app commands as ${DEPLOY_USER})"
else
    DEPLOY_USER="$(whoami)"
    RUN_AS=""
    SYSTEMCTL="sudo systemctl"
    success "Running as user ${DEPLOY_USER}"
fi

# shellcheck source=deploy/ingestion-safety.sh
source "${PROJECT_DIR}/deploy/ingestion-safety.sh"
# shellcheck source=deploy/backend-stop.sh
source "${PROJECT_DIR}/deploy/backend-stop.sh"
# shellcheck source=deploy/backend-socket.sh
source "${PROJECT_DIR}/deploy/backend-socket.sh"
# shellcheck source=deploy/backend-handover.sh
source "${PROJECT_DIR}/deploy/backend-handover.sh"
# shellcheck source=deploy/backend-tree.sh
source "${PROJECT_DIR}/deploy/backend-tree.sh"
# shellcheck source=deploy/release-plan.sh
source "${PROJECT_DIR}/deploy/release-plan.sh"
# shellcheck source=deploy/frontend-release.sh
source "${PROJECT_DIR}/deploy/frontend-release.sh"
# shellcheck source=deploy/frontend-server.sh
source "${PROJECT_DIR}/deploy/frontend-server.sh"

FRONTEND_STOPPED=false
HANDOVER_KEPT_OLD=false
restore_frontend_on_exit() {
    if [ "${FRONTEND_STOPPED}" = true ] && ! frontend_served_by_nginx; then
        warn "Deployment exited while the frontend was stopped - attempting restart"
        $SYSTEMCTL start owl-frontend-v2 || true
        sleep 3
        if $SYSTEMCTL is-active --quiet owl-frontend-v2; then
            warn "owl-frontend-v2 restarted (serving the bundle currently on disk; the release is not confirmed complete)"
        else
            fail "owl-frontend-v2 DID NOT COME BACK - start it manually: systemctl start owl-frontend-v2"
        fi
    fi
}

# Every exit, including an interrupted one, ends the log with the outcome, the
# commit, how the backend stop went and the last-good marker.
write_deploy_summary() {
    local rc="$1"
    local waited=0
    exec 1>&8 2>&8
    while kill -0 "${TEE_PID}" 2>/dev/null && [ "${waited}" -lt 20 ]; do
        sleep 0.1
        waited=$(( waited + 1 ))
    done
    {
        echo ""
        echo "==== Deploy summary - $(date) ===="
        echo "  Outcome:      ${DEPLOY_OUTCOME}"
        echo "  Exit status:  ${rc}"
        echo "  Commit:       ${NEW_COMMIT_SHORT:-not updated}"
        echo "  Backend stop: ${BACKEND_STOP_ESCALATED:-not attempted}"
        echo "  Last good:    $(cat "${LAST_GOOD_FILE:-/nonexistent}" 2>/dev/null || echo none)"
        echo "  Log:          ${LOG_FILE}"
    } | tee -a "${LOG_FILE}"
    # One row in the releases table (deploy/record_release.py); never fails the release.
    PYTHONDONTWRITEBYTECODE=1 timeout 60 "${VENV_DIR}/bin/python" "${PROJECT_DIR}/deploy/record_release.py" "${BACKEND_DIR}" \
        sha="${NEW_COMMIT:-${DEPLOY_TARGET_SHA:-}}" live_before="${LIVE_COMMIT:-}" source="${DEPLOY_SOURCE:-deploy.sh}" \
        outcome="${DEPLOY_OUTCOME}" plan="${RELEASE_PLAN:-}" frontend_build="$(frontend_current_build 2>/dev/null)" \
        started_at="${DEPLOY_START:-}" finished_at="$(date +%s)" backend_restart_at="${BACKEND_RESTART_AT:-}" \
        frontend_switch_at="${FRONTEND_SWITCH_AT:-}" healthy_at="${HEALTHY_AT:-}" log_file="${LOG_FILE}" \
        2>&1 | tee -a "${LOG_FILE}" || true
}
release_work_pause() {
    [ -n "${RELEASE_WORK_HOOK}" ] && [ "${RELEASE_TOUCHES_BACKEND}" != false ] && [ "${RELEASE_WORK_PAUSED}" = false ] || return 0
    RELEASE_WORK_PAUSED=true
    "${RELEASE_WORK_HOOK}" pause || warn "Pausing running work did not finish; the ingestion gate decides"
}
release_work_resume() {
    [ "${RELEASE_WORK_PAUSED}" = true ] || return 0
    RELEASE_WORK_PAUSED=false
    "${RELEASE_WORK_HOOK}" resume || warn "Resuming paused work did not finish; the release script resumes it"
}
on_deploy_exit() {
    local rc=$?
    trap - EXIT TERM INT HUP
    # A release that ends between starting the next backend and stopping the old one leaves the old one serving.
    backend_handover_abort_open || true
    backend_tree_settle || true
    restore_frontend_on_exit
    release_work_resume
    write_deploy_summary "${rc}"
    exit "${rc}"
}
trap on_deploy_exit EXIT
trap 'DEPLOY_OUTCOME="interrupted by SIGTERM"; exit 143' TERM
trap 'DEPLOY_OUTCOME="interrupted by SIGINT"; exit 130' INT
trap 'DEPLOY_OUTCOME="interrupted by SIGHUP"; exit 129' HUP

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

# Rollback target = last commit that PASSED a deploy health check (written only
# on success below). PREV_COMMIT is NOT safe: the docket agent pulls the tree
# before running this script, so on auto-deploys PREV == the commit under test.
LAST_GOOD_FILE="${LOG_DIR}/.last-good-commit"
# The component hashes of the last healthy release (deploy/release-plan.sh).
COMPONENTS_FILE="${LOG_DIR}/.last-good-components"
# The commit the running release reports, when it passes the health check with no local changes: the release that
# is live now. Empty when the running release is not healthy, which makes this release do every step.
LIVE_COMMIT=""
# A backend restarted outside this script (systemctl, or a pull and restart by
# hand) never passed a deploy's health check, so it was never recorded and a
# failed deploy rolled back past it. When the running release passes the same
# health check now and reports the commit its backend was started from, with
# no local changes to tracked files, that commit is recorded as known good.
if release_is_healthy; then
    RUNNING_COMMIT="$(echo "${RESPONSE}" | sed -n 's/.*"commit":"\([0-9a-f]\{40\}\)".*/\1/p')"
    if [ -n "${RUNNING_COMMIT}" ] && echo "${RESPONSE}" | grep -q '"commit_clean":true'; then
        # A release that changed no backend code leaves the backend running from an older commit; the record of the
        # last-good release says so (deploy/release-plan.sh).
        LIVE_COMMIT="$(release_live_commit "${RUNNING_COMMIT}" "${LAST_GOOD_FILE}" "${COMPONENTS_FILE}")"
        if [ -z "${LIVE_COMMIT}" ] && git cat-file -e "${RUNNING_COMMIT}^{commit}" 2>/dev/null; then
            echo "${RUNNING_COMMIT}" > "${LAST_GOOD_FILE}"
            success "Running release ${RUNNING_COMMIT:0:12} is healthy (started outside a deploy): recorded as last known-good"
            LIVE_COMMIT="${RUNNING_COMMIT}"
        fi
    fi
fi
ROLLBACK_TARGET=""
if [ -f "${LAST_GOOD_FILE}" ]; then
    CANDIDATE="$(cat "${LAST_GOOD_FILE}")"
    if git cat-file -e "${CANDIDATE}^{commit}" 2>/dev/null; then
        ROLLBACK_TARGET="${CANDIDATE}"
    fi
fi
if [ -z "${ROLLBACK_TARGET}" ]; then
    ROLLBACK_TARGET="${PREV_COMMIT}"
fi
success "Rollback target: $(git rev-parse --short "${ROLLBACK_TARGET}") (last known-good) on branch ${CURRENT_BRANCH}"

# A release of the commit that is already live and healthy changes nothing: stop here, before any check, install,
# build or restart. deploy-now.sh pins the commit it wants in DEPLOY_TARGET_SHA.
release_already_live() {
    release_fully_live "$1" "${LIVE_COMMIT}" "${COMPONENTS_FILE}" "$(frontend_current_build)" \
        "$(release_component_hashes "$1" "${ENV_FILE}")"
}
if [ -n "${DEPLOY_TARGET_SHA:-}" ] &&
    release_already_live "$(git rev-parse --verify --quiet "${DEPLOY_TARGET_SHA}^{commit}" || true)"; then
    NEW_COMMIT_SHORT="$(git rev-parse --short "${LIVE_COMMIT}")"
    success "already live: ${NEW_COMMIT_SHORT} is running and healthy; nothing installed, built or restarted"
    DEPLOY_OUTCOME="already live (nothing changed)"
    exit 0
fi

# What this release has to do: a component is skipped only when its inputs equal those of the live release.
plan_release() {
    NEW_COMPONENTS="$(release_component_hashes "$1" "${ENV_FILE}")"
    STEP_PIP="$(release_step pip "${COMPONENTS_FILE}" "${LIVE_COMMIT}" "${NEW_COMPONENTS}")"
    STEP_BACKEND="$(release_step backend "${COMPONENTS_FILE}" "${LIVE_COMMIT}" "${NEW_COMPONENTS}")"
    STEP_ENGINE="$(release_step engine "${COMPONENTS_FILE}" "${LIVE_COMMIT}" "${NEW_COMPONENTS}")"
    FRONTEND_ID="$(echo "${NEW_COMPONENTS}" | sed -n 's/^frontend=//p')"
    NPM_HASH="$(echo "${NEW_COMPONENTS}" | sed -n 's/^npm=//p')"
}
# Running ingestion matters only to a release that changes the backend, its packages or the engine: one that only
# changes the frontend leaves every worker and its code alone. Unknown plan: always check.
RELEASE_TOUCHES_BACKEND=true
# Before the pause nothing that running work uses has changed, so there is nothing to gate.
ingestion_gate() {
    local tries=3 rc=0
    [ "${RELEASE_TOUCHES_BACKEND}" = false ] && return 0
    if [ -z "${RELEASE_WORK_HOOK}" ]; then
        check_ingestion_idle
        return
    fi
    [ "${RELEASE_WORK_PAUSED}" = true ] || return 0
    # Work that started in the seconds before the hook's hold caught it is paused on its next pass.
    while [ "${tries}" -gt 0 ]; do
        rc=0
        check_ingestion_idle || rc=$?
        [ "${rc}" -eq 75 ] || return "${rc}"
        tries=$(( tries - 1 ))
        [ "${tries}" -gt 0 ] && sleep 5
    done
    return "${rc}"
}
if [ -n "${DEPLOY_TARGET_SHA:-}" ] && git rev-parse --verify --quiet "${DEPLOY_TARGET_SHA}^{commit}" >/dev/null; then
    plan_release "${DEPLOY_TARGET_SHA}"
    [ "${STEP_PIP}${STEP_BACKEND}${STEP_ENGINE}" = skipskipskip ] && RELEASE_TOUCHES_BACKEND=false
fi

step "Checking active ingestion before changing the checkout or dependencies"
ingestion_gate

step "Checking for local changes"

if ! $RUN_AS git diff --quiet 2>/dev/null || ! $RUN_AS git diff --cached --quiet 2>/dev/null; then
    warn "Local changes detected - stashing"
    $RUN_AS git stash push -m "deploy-autostash-$(date +%Y%m%d-%H%M%S)"
    success "Changes stashed"
else
    success "Working directory clean"
fi

step "Fetching and fast-forwarding ${CURRENT_BRANCH}"

source "${PROJECT_DIR}/deploy/git-update.sh"
if ! update_deploy_checkout "${CURRENT_BRANCH}"; then
    fail "Git update failed; checkout and local commits were not reset. Review the diagnostic above."
    exit 1
fi

NEW_COMMIT="$(git rev-parse HEAD)"
NEW_COMMIT_SHORT="$(git rev-parse --short HEAD)"
if [ "${PREV_COMMIT}" = "${NEW_COMMIT}" ]; then
    warn "No new commits pulled"
else
    success "Updated ${PREV_COMMIT_SHORT} -> ${NEW_COMMIT_SHORT}"
fi
if release_already_live "${NEW_COMMIT}"; then
    success "already live: ${NEW_COMMIT_SHORT} is running and healthy; nothing installed, built or restarted"
    DEPLOY_OUTCOME="already live (nothing changed)"
    exit 0
fi

plan_release "${NEW_COMMIT}"
if [ "${STEP_PIP}${STEP_BACKEND}${STEP_ENGINE}" = skipskipskip ]; then
    RELEASE_TOUCHES_BACKEND=false
else
    RELEASE_TOUCHES_BACKEND=true
fi
# The tree the new backend will run from (deploy/backend-tree.sh): the running backend reads none of it.
if [ "${RELEASE_TOUCHES_BACKEND}" = true ]; then
    step "Staging ${NEW_COMMIT_SHORT} in the tree no backend runs from"
    if ! backend_tree_stage "${NEW_COMMIT}"; then
        fail "The backend tree could not be staged; nothing was stopped or restarted."
        if [ -n "${ROLLBACK_TARGET}" ] && [ "${ROLLBACK_TARGET}" != "${NEW_COMMIT}" ]; then
            ingestion_gate
            $RUN_AS git reset --hard "${ROLLBACK_TARGET}"
            warn "Checkout returned to the running revision $(git rev-parse --short HEAD)."
        fi
        exit 1
    fi
    success "Backend tree ${BACKEND_TREE_STAGED:-(checkout)} holds ${NEW_COMMIT_SHORT}; the running backend is untouched"
    # The release's Financial views are being computed for the code deploy-now.sh pulled; if this fetch brought other
    # code, compute them again for it (backend/services/financial/view_prepare.py). Never fails the release.
    if [ -f "${BACKEND_DIR}/services/financial/view_prepare.py" ] && [ "$(id -u)" -eq 0 ]; then
        python3 "${BACKEND_DIR}/services/financial/view_prepare.py" follow || warn "Financial view prepare follow failed; release continues"
    fi
fi
PREV_FRONTEND_ID="$(frontend_current_build)"
RELEASE_PLAN="$(release_plan_summary "${COMPONENTS_FILE}" "${LIVE_COMMIT}" "${NEW_COMPONENTS}")"
success "Release plan: ${RELEASE_PLAN} (frontend build ${FRONTEND_ID:0:12}, serving ${PREV_FRONTEND_ID:0:12})"

# Party coverage: with the code being released, the share of stored payments that show a bare
# "Not identified" (no name and no stated reason) may not rise on any bank, and a newly read layout may
# not land mostly bare (backend/benchmarks/statement_automation/party_coverage_gate.py). Read-only.
# A failed gate puts the checkout back on the running revision before anything is installed or restarted.
PARTY_GATE="${BACKEND_DIR}/benchmarks/statement_automation/party_coverage_gate.py"
PARTY_BASELINE="${LOG_DIR}/party-coverage-baseline.json"
PARTY_CANDIDATE="${LOG_DIR}/party-coverage-candidate.json"
rm -f "${PARTY_CANDIDATE}"
if [ -f "${PARTY_GATE}" ]; then
    step "Party coverage gate (payments that name the other side)"
    PARTY_RC=0
    (cd "${BACKEND_DIR}" && $RUN_AS env PYTHONPATH=. "${VENV_DIR}/bin/python" -m benchmarks.statement_automation.party_coverage_gate \
        --baseline "${PARTY_BASELINE}" --out "${PARTY_CANDIDATE}") || PARTY_RC=$?
    if [ "${PARTY_RC}" -eq 1 ]; then
        fail "Party coverage gate failed: more payments would show a bare \"Not identified\". Release stopped."
        if [ -n "${ROLLBACK_TARGET}" ] && [ "${ROLLBACK_TARGET}" != "${NEW_COMMIT}" ]; then
            ingestion_gate
            $RUN_AS git reset --hard "${ROLLBACK_TARGET}"
            warn "Checkout returned to the running revision $(git rev-parse --short HEAD); services were not changed."
        fi
        exit 1
    elif [ "${PARTY_RC}" -ne 0 ]; then
        warn "Party coverage gate could not measure (exit ${PARTY_RC}); release continues without it."
        rm -f "${PARTY_CANDIDATE}"
    else
        success "Party coverage gate passed"
    fi
fi

if [ "${STEP_PIP}" = run ] && [ -n "${BACKEND_TREE_STAGED}" ]; then
    success "Backend dependencies: ${VENV_DIR} (beside the running backend's)"
elif [ "${STEP_PIP}" = run ]; then
    step "Installing backend dependencies"
    check_ingestion_idle
    $(release_build_scope) $RUN_AS "${VENV_DIR}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" --quiet
    success "Backend dependencies installed"
else
    success "Backend dependencies unchanged; pip skipped"
fi

step "Checking active ingestion before service changes"
ingestion_gate

# deploy-now.sh started the computing of this release's Financial views right after it pulled the code
# (backend/services/financial/view_prepare.py), so the restarted service finds them saved instead of every
# first visit waiting minutes. Wait for it, at most until 10 minutes after it started; a release never fails on it.
# Here, before the frontend stops, so the wait never lengthens the time the pages are down.
PREPARE_VIEWS="${BACKEND_DIR}/services/financial/view_prepare.py"
if [ -f "${PREPARE_VIEWS}" ] && [ "$(id -u)" -eq 0 ]; then
    step "Waiting for this release's Financial views"
    python3 "${PREPARE_VIEWS}" wait || warn "Financial view prepare wait failed; release continues"
fi

# Built beside the build being served (deploy/frontend-release.sh); the site stays up while it builds.
step "Building the frontend aside"
if ! frontend_build_aside "${NEW_COMMIT}" "${FRONTEND_ID}" "${NPM_HASH}"; then
    fail "Frontend build failed; nothing was stopped or restarted."
    if [ -n "${ROLLBACK_TARGET}" ] && [ "${ROLLBACK_TARGET}" != "${NEW_COMMIT}" ]; then
        ingestion_gate
        $RUN_AS git reset --hard "${ROLLBACK_TARGET}"
        warn "Checkout returned to the running revision $(git rev-parse --short HEAD)."
    fi
    exit 1
fi
cd "${PROJECT_DIR}"

step "Installing production frontend service"
if [ "$(id -u)" -eq 0 ]; then
    bash "${PROJECT_DIR}/deploy/install-frontend-service.sh"
else
    sudo bash "${PROJECT_DIR}/deploy/install-frontend-service.sh"
fi
success "Frontend service configured to serve the compiled bundle"

if [ "${STEP_ENGINE}" = run ]; then
    step "Building Docker images without replacing running containers"
    $(release_build_scope) docker compose build
fi

# Everything that can be done beside the running services is done. From here to the health check they are replaced.
step "Pausing running work: imports and engine jobs, then uploads"
release_work_pause

step "Checking ingestion before migrations and service replacement"
ingestion_gate

# Whether the old backend may stay up beside the new schema decides how this release replaces it; read before the
# migrations run (deploy/migration_safety.py).
BACKEND_REPLACE=restart
if [ "${STEP_BACKEND}" = run ] && [ "$(backend_handover_wanted)" = handover ]; then
    MIGRATION_VERDICT="$(cd "${BACKEND_DIR}" && $RUN_AS env PYTHONPATH=. "${VENV_DIR}/bin/python" ../deploy/migration_safety.py 2>&1 | tail -1 || true)"
    case "${MIGRATION_VERDICT}" in
        none|additive*)
            BACKEND_REPLACE=handover
            success "Pending migrations: ${MIGRATION_VERDICT}; the old backend can stay up beside them" ;;
        *) warn "This release replaces the backend by a restart: ${MIGRATION_VERDICT}" ;;
    esac
fi

if [ "${STEP_BACKEND}" = run ]; then
    step "Running database migrations"
    cd "${BACKEND_DIR}"
    $RUN_AS "${VENV_DIR}/bin/alembic" upgrade head
    success "Database migrations complete"
    # A prepare skipped for these migrations runs now, before the restart (view_prepare.py). Never fails the release.
    if [ -f "${PREPARE_VIEWS}" ] && [ "$(id -u)" -eq 0 ]; then
        python3 "${PREPARE_VIEWS}" after-migrations || warn "Financial view prepare after migrations failed; release continues"
    fi
    cd "${PROJECT_DIR}"
else
    success "Backend unchanged; migrations skipped"
fi

if [ "${STEP_ENGINE}" = run ]; then
    step "Refreshing Docker stack"
    check_ingestion_idle
    docker compose up -d --no-build --remove-orphans
    success "Docker stack refreshed"
else
    success "Evidence engine inputs unchanged; docker build and refresh skipped"
fi

step "Restarting services"
if [ "${STEP_BACKEND}" = run ]; then
    configure_ingestion_shutdown
    # Defined by ingestion-safety.sh, which this run sourced before the update: the
    # release that introduces the switch was sourced without it.
    if declare -F configure_backend_allocator >/dev/null; then
        configure_backend_allocator
    fi
    check_ingestion_idle
    BACKEND_RESTART_AT="$(date +%s)"
    if ! backend_tree_apply; then
        # Restarting would bring the old code back up and the release would still report healthy.
        HANDOVER_KEPT_OLD=true
        fail "The backend tree did not switch; the old backend is still serving. The release will be undone."
    elif [ "${BACKEND_REPLACE}" = handover ] && backend_handover_possible; then
        # The new backend starts beside the old one; the old one is stopped only once the new one is healthy and the
        # ingestion gate has passed again (deploy/backend-handover.sh).
        RELEASE_PLAN="${RELEASE_PLAN} replace=handover"
        if backend_handover_begin; then
            # A fatal gate here would leave the old backend running from a checkout it did not start from.
            HANDOVER_GATE=0
            check_ingestion_idle || HANDOVER_GATE=$?
            if [ "${HANDOVER_GATE}" -eq 0 ]; then
                backend_handover_commit || HANDOVER_KEPT_OLD=true
            else
                backend_handover_abort_open || true
                HANDOVER_KEPT_OLD=true
                HANDOVER_EXIT="${HANDOVER_GATE}"
            fi
        else
            HANDOVER_KEPT_OLD=true
        fi
        if [ "${HANDOVER_KEPT_OLD}" = true ]; then
            fail "The new backend did not take over; the old one is still serving. The release will be undone."
        fi
    else
        # Bounded: a backend that will not stop is escalated (SIGINT, then SIGKILL)
        # and the release always reaches its health check, last-good marker and summary.
        if ! restart_backend_bounded; then
            fail "owl-backend-v2 did not restart; the health check will fail and roll back"
        fi
    fi
else
    success "Backend unchanged; not restarted"
fi
# The frontend switches after the backend, so a new frontend never talks to the old backend.
FRONTEND_CHANGED=false
FRONTEND_SWITCH_FAILED=false
if [ "${HANDOVER_KEPT_OLD}" != true ] && [ "${PREV_FRONTEND_ID}" != "${FRONTEND_ID}" ]; then
    if frontend_switch "${FRONTEND_ID}"; then
        FRONTEND_CHANGED=true
    else
        fail "The frontend did not switch to build ${FRONTEND_ID:0:12}; the release will roll back"
        FRONTEND_SWITCH_FAILED=true
    fi
fi
FRONTEND_STOPPED=true
frontend_server_apply "${FRONTEND_CHANGED}" "${NPM_HASH}" || warn "The frontend server did not switch cleanly; the health check decides"
FRONTEND_STOPPED=false
[ "${FRONTEND_CHANGED}" = true ] && FRONTEND_SWITCH_AT="$(date +%s)"
success "V2 services restarted"

step "Running health check"
if [ "${STEP_BACKEND}" = run ] && [ "${HANDOVER_KEPT_OLD}" != true ] && [ "${BACKEND_HANDED_OVER:-}" != true ]; then
    echo "  Waiting 10s for backend initialization..."
    sleep 10
fi

HEALTHY=false
[ "${FRONTEND_SWITCH_FAILED}" = true ] && HEALTH_RETRIES=0
[ "${HANDOVER_KEPT_OLD}" = true ] && HEALTH_RETRIES=0
for i in $(seq 1 ${HEALTH_RETRIES}); do
    sleep "${HEALTH_DELAY}"
    if release_is_healthy; then
        HEALTHY_AT="$(date +%s)"
        success "Health check passed (owl-backend-v2 and the frontend server active)"
        echo "  Backend: ${RESPONSE}"
        echo "  Frontend: compiled assets served on port ${FRONTEND_PORT}"
        HEALTHY=true
        break
    fi
    echo "  Attempt ${i}/${HEALTH_RETRIES}: backend=${RESPONSE:-<no response>}, frontend compiled=$([[ -n "${FRONTEND_RESPONSE}" ]] && is_compiled_frontend "${FRONTEND_RESPONSE}" && echo yes || echo no) - waiting..."
done

if [ "${HEALTHY}" = true ]; then
    if [ "${STEP_BACKEND}" = run ]; then
        BACKEND_COMMIT="${NEW_COMMIT}"
    else
        BACKEND_COMMIT="$(release_record_value "${COMPONENTS_FILE}" backend_commit)"
    fi
    # The record first: a last-good commit without its record only makes the next release do every step.
    release_record_write "${COMPONENTS_FILE}" "${NEW_COMMIT}" "${BACKEND_COMMIT:-${LIVE_COMMIT}}" "${NEW_COMPONENTS}" ||
        rm -f "${COMPONENTS_FILE}"
    echo "${NEW_COMMIT}" > "${LAST_GOOD_FILE}"
    step "Resuming paused work: the new services are healthy"
    release_work_resume
    step "Tidying up"
    # The checkout's venv is the release tooling's; nothing that serves reads it any more.
    if [ "${STEP_PIP}" = run ] && [ -n "${BACKEND_TREE_STAGED}" ]; then
        $(release_build_scope) $RUN_AS "${PROJECT_DIR}/.venv/bin/python" -m pip install -r "${BACKEND_DIR}/requirements.txt" --quiet ||
            warn "The release tooling's packages could not be brought up to date"
    fi
    backend_venv_prune || warn "Old package folders could not be pruned"
    frontend_prune || warn "Old frontend builds could not be pruned"
    # The measure this healthy release passed with is the baseline the next release is held to.
    [ -f "${PARTY_CANDIDATE}" ] && mv -f "${PARTY_CANDIDATE}" "${PARTY_BASELINE}"
    DEPLOY_OUTCOME="deployed and healthy"
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
ROLLBACK_SHORT="$(git rev-parse --short "${ROLLBACK_TARGET}")"
ROLLBACK_WHY="health check failed"
if [ "${HANDOVER_KEPT_OLD}" = true ]; then
    ROLLBACK_WHY="the new backend did not take over"
    warn "Undoing the release: the old backend, untouched, keeps serving ${ROLLBACK_SHORT}"
elif [ "${ROLLBACK_TARGET}" = "${NEW_COMMIT}" ]; then
    fail "Health check failed - no distinct known-good commit to roll back to"
    warn "Rebuilding ${ROLLBACK_SHORT} in place (failure may be transient)"
else
    fail "Health check failed - rolling back to last known-good ${ROLLBACK_SHORT}"
fi

cd "${PROJECT_DIR}"
# With the old backend kept, the checkout goes back to the code it runs whatever is in progress: no service changes.
[ "${HANDOVER_KEPT_OLD}" = true ] || ingestion_gate
$RUN_AS git reset --hard "${ROLLBACK_TARGET}"

# The rollback serves the previous frontend build again (kept on disk) and reinstalls or restarts only what this
# release changed. A record of components is not written: the next release does every step. With the old backend
# kept, the record still describes what runs (a release that changed only the frontend leaves it naming the backend).
[ "${HANDOVER_KEPT_OLD}" = true ] || rm -f "${COMPONENTS_FILE}"
step "Rollback: dependencies"
if [ "${STEP_PIP}" = run ]; then
    check_ingestion_idle
    # With trees the previous packages are still there, beside; going back to that tree goes back to them.
    if [ -z "${BACKEND_TREE_STAGED}" ]; then
        $RUN_AS "${VENV_DIR}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" --quiet || true
    fi
fi
ROLLBACK_FRONTEND_ID="${PREV_FRONTEND_ID}"
if [ -z "${ROLLBACK_FRONTEND_ID}" ] || ! frontend_build_exists "${ROLLBACK_FRONTEND_ID}"; then
    ROLLBACK_FRONTEND_ID="$(release_component_hashes HEAD "${ENV_FILE}" | sed -n 's/^frontend=//p')"
    frontend_build_aside "$(git rev-parse HEAD)" "${ROLLBACK_FRONTEND_ID}" \
        "$(release_component_hashes HEAD "${ENV_FILE}" | sed -n 's/^npm=//p')" || true
fi

if [ "${STEP_ENGINE}" = run ]; then
    step "Rollback: rebuilding Docker stack"
    docker compose build || true
    check_ingestion_idle
    docker compose up -d --no-build --remove-orphans || true
fi

step "Rollback: restarting services"
BACKEND_HANDOVER_ROLLING_BACK=true
backend_tree_rollback "${ROLLBACK_TARGET}" || warn "The backend tree could not go back to ${ROLLBACK_SHORT}"
# A release that did not touch the backend (the plan said so) rolls back the frontend only, unless the backend
# itself is not answering. A handover that did not happen left the old backend serving: it is not stopped now.
if { [ "${RELEASE_TOUCHES_BACKEND}" = true ] && [ "${HANDOVER_KEPT_OLD}" != true ]; } ||
    ! curl -fsS --max-time 5 "${HEALTH_URL}" 2>/dev/null | grep -q '"status":"ok"'; then
    configure_ingestion_shutdown
    # Defined by ingestion-safety.sh, which this run sourced before the update: the
    # release that introduces the switch was sourced without it.
    if declare -F configure_backend_allocator >/dev/null; then
        configure_backend_allocator
    fi
    check_ingestion_idle
    restart_backend_bounded || true
fi
ROLLBACK_FRONTEND_CHANGED=false
if [ "$(frontend_current_build)" != "${ROLLBACK_FRONTEND_ID}" ] && frontend_build_exists "${ROLLBACK_FRONTEND_ID}"; then
    frontend_switch "${ROLLBACK_FRONTEND_ID}" || true
    ROLLBACK_FRONTEND_CHANGED=true
fi
FRONTEND_STOPPED=true
frontend_server_apply "${ROLLBACK_FRONTEND_CHANGED}" || true
FRONTEND_STOPPED=false

sleep 15
RESPONSE="$(curl -fsS --max-time 5 "${HEALTH_URL}" 2>/dev/null || true)"
FRONTEND_RESPONSE="$(curl -fsS --max-time 5 "${FRONTEND_URL}" 2>/dev/null || true)"
if echo "${RESPONSE}" | grep -q '"status":"ok"' &&
    ! echo "${RESPONSE}" | grep -Eq '"neo4j":"error:|"evidence_engine":"(error:|unavailable)"' &&
    is_compiled_frontend "${FRONTEND_RESPONSE}"; then
    warn "Rollback successful - running ${ROLLBACK_SHORT}"
    DEPLOY_OUTCOME="${ROLLBACK_WHY}; rolled back to ${ROLLBACK_SHORT} (healthy)"
    warn "See log: ${LOG_FILE}"
else
    fail "Rollback also failed"
    DEPLOY_OUTCOME="${ROLLBACK_WHY}; rollback to ${ROLLBACK_SHORT} also failed"
    fail "Log: ${LOG_FILE}"
fi

exit "${HANDOVER_EXIT:-1}"
