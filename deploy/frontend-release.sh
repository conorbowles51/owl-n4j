#!/usr/bin/env bash
# The frontend is built beside the one being served, never in place (sourced by deploy.sh).
#
# Layout under FRONTEND_RELEASES (default: <project>/../loupe-frontend):
#   worktree/        a git worktree of the repository, checked out at the release's commit to build; its
#                    node_modules is kept between builds and reinstalled only when package-lock.json or node change
#   builds/<id>/     one finished build per build id (the frontend hash from release-plan.sh), read-only, with every
#                    text file also stored gzip-compressed for nginx's gzip_static
#   assets/          every file of /assets of the kept builds (hard links), so a tab opened before a release can
#                    still load the pages it has not opened yet
#   current          symlink to the build being served; switched in one step (rename over it)
# The newest FRONTEND_KEEP_BUILDS builds are kept (the one served included) for open tabs and rollback.
#
# Callers provide RUN_AS (run a command as the deploy user, empty when already that user), PROJECT_DIR and the
# step/success/warn/fail log helpers.

FRONTEND_RELEASES="${FRONTEND_RELEASES:-$(cd "${PROJECT_DIR}/.." && pwd)/loupe-frontend}"
FRONTEND_KEEP_BUILDS="${FRONTEND_KEEP_BUILDS:-4}"
FRONTEND_NGINX_SITE="${FRONTEND_NGINX_SITE:-/etc/nginx/sites-enabled/loupe-frontend}"

# Builds run in the jobs fleet's low-priority slice when it exists (lx-hostpolicy, 2026-10-31), whoever started the
# release, so a build never competes with the live service; elsewhere they run as before.
release_build_scope() {
    if [ "$(id -u)" -eq 0 ] && systemctl cat fleet.slice >/dev/null 2>&1; then
        echo "systemd-run --scope --quiet --collect --slice=fleet.slice"
    fi
}

frontend_build_dir() {
    echo "${FRONTEND_RELEASES}/builds/$1"
}

# True when nginx serves the frontend (the switch from vite preview has been made).
frontend_served_by_nginx() {
    [ -e "${FRONTEND_NGINX_SITE}" ]
}

# The build id `current` points at, empty when there is none.
frontend_current_build() {
    local target
    target="$(readlink "${FRONTEND_RELEASES}/current" 2>/dev/null)" || return 0
    basename "${target}"
}

# A finished build exists for <id>.
frontend_build_exists() {
    [ -f "$(frontend_build_dir "$1")/.loupe-build-complete" ]
}

# Build commit <rev> as build <id> into builds/<id>, while whatever is served keeps being served.
# <npm_hash> decides whether node_modules has to be reinstalled.
frontend_build_aside() {
    local rev="$1" id="$2" npm_hash="$3" wt out tmp marker scope
    scope="$(release_build_scope)"
    wt="${FRONTEND_RELEASES}/worktree"
    out="$(frontend_build_dir "${id}")"
    if frontend_build_exists "${id}"; then
        success "Frontend build ${id:0:12} already exists; not rebuilt"
        return 0
    fi
    $RUN_AS mkdir -p "${FRONTEND_RELEASES}/builds" "${FRONTEND_RELEASES}/assets" || return 1
    if [ ! -e "${wt}/.git" ]; then
        (cd "${PROJECT_DIR}" && $RUN_AS git worktree add -q -f --detach "${wt}" "${rev}") || return 1
    fi
    # A job run as root in the build worktree leaves root-owned caches the deploy user cannot replace.
    [ "$(id -u)" -eq 0 ] && [ -n "${DEPLOY_USER:-}" ] && [ -d "${wt}/frontend_v2/node_modules" ] &&
        find "${wt}/frontend_v2/node_modules" -maxdepth 3 ! -user "${DEPLOY_USER}" -exec chown -R "${DEPLOY_USER}:" {} + 2>/dev/null
    (cd "${wt}" && $RUN_AS git checkout -q --detach -f "${rev}" &&
        $RUN_AS git clean -ffdxq -e frontend_v2/node_modules) || return 1
    marker="${wt}/frontend_v2/node_modules/.loupe-npm-hash"
    if [ "$(cat "${marker}" 2>/dev/null)" != "${npm_hash}" ]; then
        step "Installing frontend dependencies in the build worktree (package-lock or node changed)"
        (cd "${wt}/frontend_v2" && $RUN_AS rm -f "${marker}" && $scope $RUN_AS nice -n 15 npm ci --silent) || return 1
        $RUN_AS mkdir -p "$(dirname "${marker}")" && echo "${npm_hash}" | $RUN_AS tee "${marker}" >/dev/null
    else
        success "Frontend dependencies unchanged; node_modules kept"
    fi
    tmp="${FRONTEND_RELEASES}/builds/.building-${id}"
    $RUN_AS rm -rf "${tmp}"
    (cd "${wt}/frontend_v2" && $RUN_AS rm -rf node_modules/.vite &&
        $scope $RUN_AS env LOUPE_BUILD_ID="${id}" nice -n 15 npm run build -- --outDir "${tmp}" --emptyOutDir) || return 1
    frontend_precompress "${tmp}" || return 1
    echo "commit=${rev}" | $RUN_AS tee "${tmp}/.loupe-build-complete" >/dev/null
    $RUN_AS chmod -R a-w "${tmp}"
    $RUN_AS chmod u+w "${tmp}"
    $RUN_AS mv -T "${tmp}" "${out}" || return 1
    $RUN_AS chmod u-w "${out}"
    success "Frontend built aside as ${id:0:12} (served build unchanged)"
}

# Store a gzip copy next to every text file (-n: no name or time inside, so the same input gives the same bytes).
frontend_precompress() {
    find "$1" -type f \( -name '*.js' -o -name '*.css' -o -name '*.html' -o -name '*.json' -o -name '*.svg' \
        -o -name '*.map' -o -name '*.txt' -o -name '*.wasm' \) -print0 |
        $RUN_AS xargs -0 -r gzip -9 -k -n -f
}

# Point `current` at build <id> in one step and keep the asset pool covering the kept builds.
frontend_switch() {
    local id="$1" link="${FRONTEND_RELEASES}/current"
    frontend_build_exists "${id}" || { fail "No finished frontend build ${id}"; return 1; }
    # Old tabs' files stay reachable: link this build's assets into the pool before index.html points at them.
    # Copy the files, never the directory itself: the build's assets/ is read-only and "cp -a dir/." would give the
    # pool that mode, so the next release could not add its files (release of 9e88a187, 2026-10-31 02:06).
    $RUN_AS chmod u+w "${FRONTEND_RELEASES}/assets" || return 1
    (cd "$(frontend_build_dir "${id}")/assets" && find . -mindepth 1 -maxdepth 1 -print0 |
        $RUN_AS xargs -0 -r cp -al -n -t "${FRONTEND_RELEASES}/assets/" 2>/dev/null) ||
        (cd "$(frontend_build_dir "${id}")/assets" && find . -mindepth 1 -maxdepth 1 -print0 |
            $RUN_AS xargs -0 -r cp -a -n -t "${FRONTEND_RELEASES}/assets/") || return 1
    $RUN_AS ln -sfn "builds/${id}" "${link}.new" && $RUN_AS mv -T "${link}.new" "${link}" || return 1
    $RUN_AS touch -h "$(frontend_build_dir "${id}")" 2>/dev/null || true
    success "Frontend now serves build ${id:0:12}"
}

# Keep the newest FRONTEND_KEEP_BUILDS builds (current always), and only their files in the asset pool.
frontend_prune() {
    local current keep=() b f name
    current="$(frontend_current_build)"
    [ -n "${current}" ] || return 0
    keep+=("${current}")
    while IFS= read -r b; do
        [ "${#keep[@]}" -ge "${FRONTEND_KEEP_BUILDS}" ] && break
        [ "${b}" = "${current}" ] && continue
        frontend_build_exists "${b}" && keep+=("${b}")
    done < <(cd "${FRONTEND_RELEASES}/builds" && ls -1t 2>/dev/null)
    for b in $(cd "${FRONTEND_RELEASES}/builds" && ls -1A); do
        printf '%s\n' "${keep[@]}" | grep -qxF "${b}" && continue
        $RUN_AS chmod -R u+w "$(frontend_build_dir "${b}")" && $RUN_AS rm -rf "$(frontend_build_dir "${b}")"
    done
    for f in "${FRONTEND_RELEASES}"/assets/*; do
        [ -e "${f}" ] || continue
        name="$(basename "${f}")"
        local used=false
        for b in "${keep[@]}"; do [ -e "$(frontend_build_dir "${b}")/assets/${name}" ] && { used=true; break; }; done
        [ "${used}" = true ] || $RUN_AS rm -f "${f}"
    done
}
