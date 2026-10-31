#!/usr/bin/env bash
# What a release has to do, decided from its inputs (sourced by deploy.sh and deploy-now.sh).
#
# Each component of a release is identified by a hash of exactly the inputs that change its output:
#   frontend  the frontend_v2 tree, the VITE_* settings and the node version (the built bundle)
#   npm       frontend_v2/package-lock.json and the node version (node_modules)
#   pip       backend/requirements.txt (the backend virtualenv)
#   backend   the backend tree, the scripts that configure its unit, and .env (the running backend)
#   engine    evidence-engine/, docker-compose.yml, the backend tree and .env (the engine images and containers)
# A healthy release writes its hashes next to the last-good commit. The next release skips a component only when
# its hash equals the one recorded for the release that is live now; a missing or unreadable record means do
# everything (the old behaviour).

RELEASE_COMPONENTS="frontend npm pip backend engine"

# Git object id of <rev>:<path>, or "none" when the path does not exist at that revision.
_release_object() {
    git rev-parse --verify --quiet "$1:$2" 2>/dev/null || echo none
}

# sha1 of stdin, short and portable.
_release_digest() {
    sha1sum | cut -c1-40
}

# The .env lines that reach the built bundle (VITE_*), sorted, and the rest of .env (everything else).
_release_env_part() {
    local env_file="$1" part="$2"
    [ -f "${env_file}" ] || { echo "no-env"; return; }
    if [ "${part}" = vite ]; then
        grep -E '^[[:space:]]*(export[[:space:]]+)?VITE_' "${env_file}" | sed 's/^[[:space:]]*//' | LC_ALL=C sort
    else
        grep -vE '^[[:space:]]*(export[[:space:]]+)?VITE_' "${env_file}" | LC_ALL=C sort
    fi
}

# Print "name=hash" for every component of <rev>. Run inside the repository.
release_component_hashes() {
    local rev="$1" env_file="$2" node_version backend_tree env_rest
    node_version="$(node --version 2>/dev/null || echo no-node)"
    backend_tree="$(_release_object "${rev}" backend)"
    env_rest="$(_release_env_part "${env_file}" rest | _release_digest)"
    echo "frontend=$( { _release_object "${rev}" frontend_v2; _release_env_part "${env_file}" vite; echo "${node_version}"; } | _release_digest)"
    echo "npm=$( { _release_object "${rev}" frontend_v2/package-lock.json; echo "${node_version}"; } | _release_digest)"
    echo "pip=$(_release_object "${rev}" backend/requirements.txt)"
    echo "backend=$( { echo "${backend_tree}"; _release_object "${rev}" deploy/ingestion-safety.sh; _release_object "${rev}" deploy/backend-stop.sh; echo "${env_rest}"; } | _release_digest)"
    echo "engine=$( { _release_object "${rev}" evidence-engine; _release_object "${rev}" docker-compose.yml; echo "${backend_tree}"; echo "${env_rest}"; } | _release_digest)"
}

# The value of <name> in a "name=value" file, empty when absent.
release_record_value() {
    local file="$1" name="$2"
    [ -f "${file}" ] || return 0
    sed -n "s/^${name}=//p" "${file}" | head -1
}

# "run" or "skip" for <component>: skip only when the recorded live release is <live_commit> and its hash for the
# component equals the new one.
release_step() {
    local component="$1" recorded="$2" live_commit="$3" new_hashes="$4" old new
    [ -n "${live_commit}" ] || { echo run; return; }
    [ "$(release_record_value "${recorded}" commit)" = "${live_commit}" ] || { echo run; return; }
    old="$(release_record_value "${recorded}" "${component}")"
    new="$(echo "${new_hashes}" | sed -n "s/^${component}=//p" | head -1)"
    if [ -n "${old}" ] && [ -n "${new}" ] && [ "${old}" = "${new}" ]; then echo skip; else echo run; fi
}

# One line naming what runs and what is skipped, for logs.
release_plan_summary() {
    local recorded="$1" live_commit="$2" new_hashes="$3" c out=""
    for c in ${RELEASE_COMPONENTS}; do
        out="${out}${out:+ }${c}=$(release_step "${c}" "${recorded}" "${live_commit}" "${new_hashes}")"
    done
    echo "${out}"
}

# Record the hashes of a release that passed its health check, with the commit its running backend was started from
# (the release's own commit when it restarted the backend, else the one recorded before).
release_record_write() {
    local recorded="$1" commit="$2" backend_commit="$3" new_hashes="$4"
    { echo "commit=${commit}"; echo "backend_commit=${backend_commit}"; echo "${new_hashes}"; } > "${recorded}.tmp" &&
        mv -f "${recorded}.tmp" "${recorded}"
}

# <commit> is fully live: it is the live release (release_live_commit), the record of the last-good release is for
# it and names the frontend build being served, and every component hash of <commit> now (<new_hashes>, which also
# cover .env and node) equals the recorded one. A backend restarted by hand at a commit is not enough (its frontend,
# engine and migrations were never released), nor is the same commit with a changed .env.
release_fully_live() {
    local commit="$1" live="$2" recorded="$3" serving="$4" new_hashes="$5" c
    [ -n "${commit}" ] && [ "${commit}" = "${live}" ] &&
        [ "$(release_record_value "${recorded}" commit)" = "${commit}" ] &&
        [ -n "${serving}" ] && [ "$(release_record_value "${recorded}" frontend)" = "${serving}" ] || return 1
    for c in ${RELEASE_COMPONENTS}; do
        [ "$(release_step "${c}" "${recorded}" "${live}" "${new_hashes}")" = skip ] || return 1
    done
}

# The release that is live, given the commit the healthy running backend reports it was started from: the last-good
# commit when the backend was started from it, or when the last-good release did not restart the backend and recorded
# that this backend commit carried on. Empty when the running backend is not explained by the last-good release.
release_live_commit() {
    local running="$1" last_good_file="$2" recorded="$3" last_good
    last_good="$(cat "${last_good_file}" 2>/dev/null || true)"
    [ -n "${running}" ] && [ -n "${last_good}" ] || return 0
    if [ "${running}" = "${last_good}" ]; then
        echo "${last_good}"
    elif [ "$(release_record_value "${recorded}" commit)" = "${last_good}" ] &&
        [ "$(release_record_value "${recorded}" backend_commit)" = "${running}" ]; then
        echo "${last_good}"
    fi
}
