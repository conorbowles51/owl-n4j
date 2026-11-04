#!/usr/bin/env bash

# Fetch one branch without relying on shared FETCH_HEAD or pull configuration.
# Never reset a deployment checkout or discard server-only commits.
# DEPLOY_TARGET_SHA (set by deploy-now.sh to the commit it prepared) pins the release: the checkout moves to exactly
# that commit, never to something pushed after it; newer commits go out with the next release.
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
    # GitHub refuses a good key on and off (4 Nov 2026: 3 of 6 tries 'Permission denied (publickey)' with the same key
    # and address); one refusal must not fail a release after a ten-minute prepare. Retry with a growing pause.
    local delay fetched=false
    for delay in ${GIT_UPDATE_FETCH_DELAYS-5 15 30} last; do
        if git fetch --no-write-fetch-head origin "+refs/heads/${branch}:refs/remotes/origin/${branch}"; then
            fetched=true; break
        fi
        [ "${delay}" = last ] && break
        echo "Fetch of ${branch} failed; retrying in ${delay}s." >&2
        sleep "${delay}"
    done
    if [ "${fetched}" = false ]; then
        # A pinned release whose commit deploy-now.sh already fetched onto origin/<branch> needs nothing new from GitHub.
        if [ -n "${DEPLOY_TARGET_SHA:-}" ] && git rev-parse --verify --quiet "${DEPLOY_TARGET_SHA}^{commit}" >/dev/null &&
            git merge-base --is-ancestor "${DEPLOY_TARGET_SHA}" "refs/remotes/origin/${branch}" 2>/dev/null; then
            echo "Fetch of ${branch} failed every try; pinned ${DEPLOY_TARGET_SHA} is already on origin/${branch}, continuing." >&2
        else
            echo "Fetch of ${branch} failed every try." >&2
            return 1
        fi
    fi
    target="$(git rev-parse --verify "refs/remotes/origin/${branch}^{commit}")" || return 1
    if [ -n "${DEPLOY_TARGET_SHA:-}" ]; then
        local pinned
        pinned="$(git rev-parse --verify --quiet "${DEPLOY_TARGET_SHA}^{commit}")" || {
            echo "Pinned release commit ${DEPLOY_TARGET_SHA} is not in this repository." >&2
            return 1
        }
        if ! git merge-base --is-ancestor "${pinned}" "${target}"; then
            echo "Pinned release commit ${DEPLOY_TARGET_SHA} is not on origin/${branch}." >&2
            return 1
        fi
        target="${pinned}"
    fi
    if ! git merge-base --is-ancestor HEAD "${target}"; then
        echo "Deploy checkout has commits not contained in origin/${branch}; preserved without reset." >&2
        git --no-pager log --oneline --left-right "HEAD...${target}" >&2
        return 1
    fi
    git merge --ff-only "${target}"
}
