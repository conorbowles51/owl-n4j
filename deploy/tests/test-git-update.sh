#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/git-update.sh"
scratch="$(mktemp -d)"
trap 'rm -rf "${scratch}"' EXIT
git init -q --bare "${scratch}/origin.git"
git init -q -b main "${scratch}/writer"
cd "${scratch}/writer"
git config user.name Test
git config user.email test@example.invalid
echo initial > file
git add file
git commit -qm initial
git remote add origin "${scratch}/origin.git"
git push -q origin main
git clone -q -b main "${scratch}/origin.git" "${scratch}/deploy"
echo next >> file
git commit -qam next
git push -q origin main
target="$(git rev-parse HEAD)"
cd "${scratch}/deploy"
git config user.name Test
git config user.email test@example.invalid
git config --add branch.main.merge refs/heads/another
# Deliberately ambiguous shared fetch state must be irrelevant.
printf '%s\t\tbranch main\n%s\t\tbranch another\n' "$(git rev-parse HEAD)" "${target}" > .git/FETCH_HEAD
before_fetch="$(cat .git/FETCH_HEAD)"
update_deploy_checkout main
test "$(git rev-parse HEAD)" = "${target}"
test "$(cat .git/FETCH_HEAD)" = "${before_fetch}"
update_deploy_checkout main
if update_deploy_checkout another; then echo 'Expected branch mismatch rejection'; exit 1; fi
echo local > local
git add local
git commit -qm server-only
local_head="$(git rev-parse HEAD)"
if update_deploy_checkout main; then echo 'Expected local commit preservation'; exit 1; fi
test "$(git rev-parse HEAD)" = "${local_head}"
test -f local
cd "${scratch}/writer"
echo remote > remote
git add remote
git commit -qm remote-only
git push -q origin main
cd "${scratch}/deploy"
if update_deploy_checkout main; then echo 'Expected divergence rejection'; exit 1; fi
test "$(git rev-parse HEAD)" = "${local_head}"
test -f local
# A pinned release lands on exactly the pinned commit, not on newer commits on origin.
git clone -q -b main "${scratch}/origin.git" "${scratch}/pinned"
cd "${scratch}/writer"
pinned="$(git rev-parse HEAD)"
echo newer >> file
git commit -qam newer
git push -q origin main
cd "${scratch}/pinned"
git reset -q --hard HEAD~1
DEPLOY_TARGET_SHA="${pinned}" update_deploy_checkout main
test "$(git rev-parse HEAD)" = "${pinned}"
if DEPLOY_TARGET_SHA=0123456789abcdef0123456789abcdef01234567 update_deploy_checkout main; then
    echo 'Expected an unknown pinned commit to be refused'; exit 1
fi
test "$(git rev-parse HEAD)" = "${pinned}"
update_deploy_checkout main
test "$(git rev-parse HEAD)" = "$(git -C "${scratch}/writer" rev-parse HEAD)"
echo 'Git update regression checks passed'
