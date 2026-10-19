#!/usr/bin/env bash

# Fetch one branch without relying on shared FETCH_HEAD or pull configuration.
# Never reset a deployment checkout or discard server-only commits.
update_deploy_checkout() {
    local branch="$1" target current
    git check-ref-format "refs/heads/${branch}" >/dev/null || return 1
    current="$(git symbolic-ref --quiet --short HEAD)" || return 1
    if [ "${current}" != "${branch}" ]; then
        echo "Deploy branch ${branch} differs from checked-out branch ${current}; refusing to merge across branches." >&2
        return 1
    fi
    if [ -n "$(git ls-files -u)" ]; then
        echo "Unresolved index conflicts exist; resolve them before deployment." >&2
        return 1
    fi
    git fetch --no-write-fetch-head origin "+refs/heads/${branch}:refs/remotes/origin/${branch}" || return 1
    target="$(git rev-parse --verify "refs/remotes/origin/${branch}^{commit}")" || return 1
    if ! git merge-base --is-ancestor HEAD "${target}"; then
        echo "Deploy checkout has commits not contained in origin/${branch}; preserved without reset." >&2
        git --no-pager log --oneline --left-right "HEAD...${target}" >&2
        return 1
    fi
    git merge --ff-only "${target}"
}
