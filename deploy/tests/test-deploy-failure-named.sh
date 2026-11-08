#!/usr/bin/env bash
# A release stopped by a failing command under set -e names the step and the command in its summary Outcome (8 Nov:
# two releases ended "deploy exit 1" with only "see the last [FAIL] above" and no [FAIL] line). Runs deploy.sh's own
# step/trap/outcome lines in a scratch script; nothing on the host is touched.
set -euo pipefail
src="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/deploy.sh"
tmp="$(mktemp -d)"; trap 'rm -rf -- "${tmp}"' EXIT
{
    echo 'set -euo pipefail; BLUE=; NC=; BOLD='
    grep -E '^step\(\) ' "${src}"
    sed -n '/^DEPLOY_OUTCOME_DEFAULT=/,/^trap .* ERR$/p' "${src}"
    echo 'on_deploy_exit() {'
    echo '    local rc=$?'
    sed -n '/^on_deploy_exit() {/,/^}/p' "${src}" | sed -n '/^    trap - EXIT/,/^    fi$/p'
    echo '    echo "Outcome: ${DEPLOY_OUTCOME}"; exit "${rc}"'
    echo '}'
    echo 'trap on_deploy_exit EXIT'
    echo 'settings() { true; bash -c "exit 3"; }'
    echo 'step "Pre-flight checks"'
    echo 'if false; then :; fi; false || true'
    echo 'step "Chroma search settings"'
    echo 'settings'
    echo 'echo not reached'
} > "${tmp}/release.sh"
grep -q 'DEPLOY_FAILED_AT' "${tmp}/release.sh" || { echo "FAIL: deploy.sh records no failing command"; exit 1; }
set +e; out="$(bash "${tmp}/release.sh" 2>&1)"; rc=$?; set -e
[ "${rc}" -eq 3 ] || { echo "FAIL: exit ${rc}, wanted 3: ${out}"; exit 1; }
grep -q 'Outcome: failed in step "Chroma search settings", line [0-9]*: bash -c "exit 3" (exit 3)' <<<"${out}" \
    || { echo "FAIL: outcome does not name the step and command: ${out}"; exit 1; }
! grep -q 'not reached' <<<"${out}" || { echo "FAIL: the release went on after the failure"; exit 1; }
echo "PASS deploy failure named"
