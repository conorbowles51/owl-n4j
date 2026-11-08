# Shared helpers for the deploy/ci scan scripts. Source this; do not run it.
#
# Everything heavy runs at nice 15 / ionice idle, and every scanner checks memory
# pressure before starting (the box serves the live app). Tools are installed once
# into CI_TOOLS_DIR by bootstrap-tools.sh and reused.

CI_TOOLS_DIR="${CI_TOOLS_DIR:-/mnt/owl-data/fin-wt/ci-tools}"
CI_REPORTS_DIR="${CI_REPORTS_DIR:-/mnt/owl-data/fin-wt/ci-reports}"
CI_NICE="nice -n 15 ionice -c3"

# Pinned tool versions. Bump deliberately; bootstrap-tools.sh verifies each
# download against the project's published checksum file.
GITLEAKS_VERSION=8.30.1
TRIVY_VERSION=0.76.2
TERRAFORM_VERSION=1.17.1

ci_log() { echo "$(date -u +%FT%TZ) $*"; }

# Memory pressure guard: PSI "full" avg60 as an integer percentage.
psi_full() {
  awk '/^full/ {split($3,a,"="); printf "%d\n", a[2]}' /proc/pressure/memory 2>/dev/null || echo 0
}

# Abort guard for heavy stages (trivy image scans). Returns 1 when the box is
# under memory pressure; callers must record the skip in the report — a clipped
# scan is reported as clipped, never as a clean pass.
psi_ok() {
  local limit="${1:-50}" now
  now=$(psi_full)
  if [ "$now" -ge "$limit" ]; then
    ci_log "memory PSI full ${now}% >= ${limit}%: refusing to start a heavy scan" >&2
    return 1
  fi
}

gitleaks_bin()  { echo "$CI_TOOLS_DIR/gitleaks"; }
trivy_bin()     { echo "$CI_TOOLS_DIR/trivy"; }
terraform_bin() { echo "$CI_TOOLS_DIR/terraform"; }
pip_audit_bin() { echo "$CI_TOOLS_DIR/venv/bin/pip-audit"; }

tools_ready() {
  [ -x "$(gitleaks_bin)" ] && [ -x "$(trivy_bin)" ] && [ -x "$(pip_audit_bin)" ]
}
