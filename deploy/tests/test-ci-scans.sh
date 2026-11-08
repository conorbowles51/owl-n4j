#!/usr/bin/env bash
# The scan gates catch what they exist to catch: a planted secret in a fresh repo's
# history is found by secret-scan.sh, and a planted vulnerable pin is found by
# deps-scan.sh. Both fail on the old code (no deploy/ci scripts, nothing caught).
# Needs the scan tools (deploy/ci/bootstrap-tools.sh); skips with a message when
# they are not installed rather than passing silently.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root:?}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ci="${source_dir}/ci"
. "${ci}/ci-lib.sh"

fail() { echo "FAIL: $*"; exit 1; }
if ! [ -x "$(gitleaks_bin)" ] || ! [ -x "$(pip_audit_bin)" ]; then
    echo "SKIP: scan tools not installed (run deploy/ci/bootstrap-tools.sh first)"; exit 0
fi

# --- A planted secret in git history is caught, its value never in the report ----
planted_repo="${test_root}/leaky"
mkdir -p "${planted_repo}"
git -C "${planted_repo}" init -q
# A fake token: GitHub-PAT shape with random content, so it belongs to nobody and
# is not on gitleaks' example-value allowlist (AWS's documented AKIA example is,
# and is deliberately not found).
planted="ghp_$(head -c 200 /dev/urandom | tr -dc 'A-Za-z0-9' | head -c 36)"
printf 'token = %s\n' "${planted}" > "${planted_repo}/settings.ini"
git -C "${planted_repo}" -c user.name=t -c user.email=t@t add settings.ini
git -C "${planted_repo}" -c user.name=t -c user.email=t@t commit -qm "add settings"
# The leak is then "deleted" — history still holds it, and that is what the scan reads.
git -C "${planted_repo}" -c user.name=t -c user.email=t@t rm -q settings.ini
git -C "${planted_repo}" -c user.name=t -c user.email=t@t commit -qm "remove settings"

out="${test_root}/secret-out"
if CI_FAIL_ON_NEW=1 bash "${ci}/secret-scan.sh" "${planted_repo}" "${out}" > "${test_root}/secret.log" 2>&1; then
    fail "secret-scan passed a repo with a planted secret in history"
fi
[ -s "${out}/gitleaks.json" ] || fail "no gitleaks report written"
python3 -c "
import json, sys
f = json.load(open('${out}/gitleaks.json'))
sys.exit(0 if len(f) >= 1 else 1)
" || fail "planted secret not in the report"
# The secret's value must appear nowhere in the output directory.
if grep -rq "${planted}" "${out}"; then
    fail "the planted secret's value is printed in the report"
fi

# --- A planted vulnerable pin is caught by the dependency scan -------------------
dep_src="${test_root}/dep-src"
mkdir -p "${dep_src}/backend"
# urllib3 1.26.0: years of published advisories; any fixed tool version knows several.
echo "urllib3==1.26.0" > "${dep_src}/backend/requirements.txt"
dep_out="${test_root}/dep-out"
CI_LIVE_VENV=/nonexistent bash "${ci}/deps-scan.sh" "${dep_src}" "${dep_out}" > "${test_root}/deps.log" 2>&1 \
    || fail "deps-scan errored (see ${test_root}/deps.log)"
python3 -c "
import json, sys
c = json.load(open('${dep_out}/deps-counts.json'))
n = c.get('pip_audit_vulns')
sys.exit(0 if isinstance(n, int) and n >= 1 else 1)
" || fail "planted vulnerable pin (urllib3==1.26.0) not caught"

echo "ok: planted secret caught (value never printed) and planted vulnerable pin caught"
