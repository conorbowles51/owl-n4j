#!/usr/bin/env bash
# Files a root job leaves in the build worktree, at any depth, go back to the deploy user before the build
# (30 Oct 23:45: a root-owned node_modules/.vite-temp failed the release). Needs root to own files as someone else.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo "test-frontend-reclaim: skipped (needs root)"; exit 0; fi
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
success() { :; }; step() { :; }
PROJECT_DIR="${test_root}"
# shellcheck source=deploy/frontend-release.sh
source "${source_dir}/frontend-release.sh"
DEPLOY_USER=nobody
wt="${test_root}/worktree"
mkdir -p "${wt}/frontend_v2/node_modules/.vite-temp" "${wt}/frontend_v2/node_modules/pkg/dist/esm/deep/er"
touch "${wt}/frontend_v2/node_modules/.vite-temp/vitest.config.mjs" \
      "${wt}/frontend_v2/node_modules/pkg/dist/esm/deep/er/root-file.js" "${wt}/stray-root-file"
chown -R nobody: "${wt}"
# Root-owned files under directories the deploy user owns, deeper than the old 3-level search reached.
chown root: "${wt}/frontend_v2/node_modules/pkg/dist/esm/deep/er/root-file.js" "${wt}/stray-root-file"
chown -R root: "${wt}/frontend_v2/node_modules/.vite-temp"
frontend_reclaim_worktree "${wt}"
left="$(find "${wt}" ! -user nobody | wc -l)"
test "${left}" = 0 || { echo "still not owned by the deploy user:"; find "${wt}" ! -user nobody; exit 1; }
# Not root, or no deploy user: nothing is touched and nothing fails.
chown root: "${wt}/stray-root-file"
DEPLOY_USER="" frontend_reclaim_worktree "${wt}"
test "$(stat -c %U "${wt}/stray-root-file")" = root
echo "test-frontend-reclaim: passed"
