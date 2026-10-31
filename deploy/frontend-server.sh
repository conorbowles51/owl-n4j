#!/usr/bin/env bash
# Which program serves Loupe on FRONTEND_PORT, and switching between them (sourced by deploy.sh after
# frontend-release.sh).
#
# deploy/frontend-server.conf names the server a release leaves running: "nginx" (static files from the current
# build, /api proxied; nothing stops during a release) or "vite" (the owl-frontend-v2 unit running vite preview;
# it reads the build at start, so it is restarted when the build changes). Going back to vite preview is a one-line
# change of that file and a release; nothing else has to be undone.

FRONTEND_UNIT="${FRONTEND_UNIT:-owl-frontend-v2}"
FRONTEND_NGINX_TEMPLATE="${PROJECT_DIR}/deploy/nginx-loupe-frontend.conf"
FRONTEND_NGINX_AVAILABLE="${FRONTEND_NGINX_AVAILABLE:-/etc/nginx/sites-available/loupe-frontend}"

frontend_server_wanted() {
    local wanted
    wanted="$(grep -v '^[[:space:]]*\(#\|$\)' "${PROJECT_DIR}/deploy/frontend-server.conf" 2>/dev/null | head -1 | tr -d '[:space:]')"
    case "${wanted}" in
        nginx) echo nginx ;;
        *) echo vite ;;
    esac
}

# The nginx site for this checkout, rendered from the template.
# The API target is the one the vite proxy uses: VITE_API_PROXY_TARGET from .env, else http://0.0.0.0:<API_PORT>;
# its host:port is also the Host header the backend sees.
frontend_nginx_render() {
    local target="${VITE_API_PROXY_TARGET:-}"
    [ -n "${target}" ] || target="http://0.0.0.0:${API_PORT:-8002}"
    target="${target#http://}"; target="${target%%/*}"
    sed -e "s|@PORT@|${FRONTEND_PORT}|g" -e "s|@RELEASES@|${FRONTEND_RELEASES}|g" \
        -e "s|@API_HOST@|${target}|g" -e "s|@API@|${target}|g" "${FRONTEND_NGINX_TEMPLATE}"
}

# The server in use is up (the health check's unit test).
frontend_server_active() {
    if frontend_served_by_nginx; then
        $SYSTEMCTL is-active --quiet nginx
    else
        $SYSTEMCTL is-active --quiet "${FRONTEND_UNIT}"
    fi
}

# vite preview serves frontend_v2/dist: make it the current build (a symlink), replacing an in-place build.
frontend_point_preview_at_current() {
    local dist="${PROJECT_DIR}/frontend_v2/dist" want
    want="${FRONTEND_RELEASES}/current"
    [ "$(readlink "${dist}" 2>/dev/null)" = "${want}" ] && return 0
    $RUN_AS rm -rf "${dist}.old" && { [ ! -e "${dist}" ] || $RUN_AS mv -T "${dist}" "${dist}.old"; } &&
        $RUN_AS ln -sfn "${want}" "${dist}" && $RUN_AS rm -rf "${dist}.old"
}

# vite preview runs from the live checkout's node_modules. Until now every release ran npm ci there; the builds no
# longer do, so the live install follows package-lock here: a marker records the install's lock hash (absent: the
# install made by the last in-place release, recorded as current). Prints "stale" when it must be reinstalled.
frontend_live_modules_state() {
    local npm_hash="$1" marker="${PROJECT_DIR}/frontend_v2/node_modules/.loupe-npm-hash"
    [ -d "${PROJECT_DIR}/frontend_v2/node_modules" ] || { echo stale; return; }
    if [ ! -f "${marker}" ]; then
        echo "${npm_hash}" | $RUN_AS tee "${marker}" >/dev/null
    fi
    [ "$(cat "${marker}" 2>/dev/null)" = "${npm_hash}" ] && echo current || echo stale
}

frontend_live_modules_install() {
    local npm_hash="$1" marker="${PROJECT_DIR}/frontend_v2/node_modules/.loupe-npm-hash"
    step "Installing the live checkout's frontend dependencies for vite preview (package-lock changed)"
    (cd "${PROJECT_DIR}/frontend_v2" && $RUN_AS rm -f "${marker}" && $RUN_AS npm ci --silent) || return 1
    echo "${npm_hash}" | $RUN_AS tee "${marker}" >/dev/null
}

# Leave the wanted server serving the current build. <changed> is true when `current` moved in this release;
# <npm_hash> is the release's package-lock hash. Returns non-zero when nothing serves the frontend afterwards.
frontend_server_apply() {
    local changed="$1" npm_hash="${2:-}" wanted modules=current
    wanted="$(frontend_server_wanted)"
    if [ "${wanted}" = nginx ]; then
        local rendered
        rendered="$(frontend_nginx_render)"
        if ! frontend_served_by_nginx || [ "$(cat "${FRONTEND_NGINX_AVAILABLE}" 2>/dev/null)" != "${rendered}" ]; then
            step "Serving the frontend from nginx"
            printf '%s\n' "${rendered}" > "${FRONTEND_NGINX_AVAILABLE}.new" &&
                mv -f "${FRONTEND_NGINX_AVAILABLE}.new" "${FRONTEND_NGINX_AVAILABLE}"
            ln -sfn "${FRONTEND_NGINX_AVAILABLE}" "${FRONTEND_NGINX_SITE}"
            if ! nginx -t -q; then
                fail "nginx rejected the Loupe site; vite preview keeps serving"
                rm -f "${FRONTEND_NGINX_SITE}"
                $SYSTEMCTL start "${FRONTEND_UNIT}" || true
                return 1
            fi
            # The port is free only once vite preview has stopped; the gap is the time between these two lines.
            $SYSTEMCTL stop "${FRONTEND_UNIT}" 2>/dev/null || true
            $SYSTEMCTL disable --quiet "${FRONTEND_UNIT}" 2>/dev/null || true
            if ! { $SYSTEMCTL reload nginx 2>/dev/null || $SYSTEMCTL start nginx; }; then
                fail "nginx did not take the Loupe site; going back to vite preview"
                rm -f "${FRONTEND_NGINX_SITE}"
                $SYSTEMCTL reload nginx || true
                $SYSTEMCTL enable --quiet "${FRONTEND_UNIT}" || true
                $SYSTEMCTL start "${FRONTEND_UNIT}"
                return 1
            fi
            success "nginx serves :${FRONTEND_PORT} from ${FRONTEND_RELEASES}/current"
        else
            success "nginx serves :${FRONTEND_PORT}; the build switch needed no restart"
        fi
        return 0
    fi
    [ -n "${npm_hash}" ] && modules="$(frontend_live_modules_state "${npm_hash}")"
    # vite preview: it indexes the files when it starts, so a new build (or a first switch of dist to the build
    # directory) needs a restart, a few seconds.
    if frontend_served_by_nginx; then
        step "Serving the frontend from vite preview again"
        frontend_point_preview_at_current || return 1
        rm -f "${FRONTEND_NGINX_SITE}"
        $SYSTEMCTL reload nginx || true
        $SYSTEMCTL enable --quiet "${FRONTEND_UNIT}" || true
        $SYSTEMCTL restart "${FRONTEND_UNIT}"
    elif [ "${changed}" = true ] || [ "${modules}" = stale ] || ! $SYSTEMCTL is-active --quiet "${FRONTEND_UNIT}" ||
        [ "$(readlink "${PROJECT_DIR}/frontend_v2/dist" 2>/dev/null)" != "${FRONTEND_RELEASES}/current" ]; then
        $SYSTEMCTL stop "${FRONTEND_UNIT}" || true
        if [ "${modules}" = stale ]; then
            frontend_live_modules_install "${npm_hash}" || warn "npm ci in the live checkout failed"
        fi
        frontend_point_preview_at_current || { $SYSTEMCTL start "${FRONTEND_UNIT}"; return 1; }
        $SYSTEMCTL start "${FRONTEND_UNIT}"
    fi
}
