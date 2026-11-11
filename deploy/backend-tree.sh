#!/usr/bin/env bash
# The backend runs from a tree of its own, never from the checkout a release moves (sourced by deploy.sh and rollback.sh;
# deploy-now.sh runs it with "stage <commit>").
#
# A release moves the live checkout long before it replaces the backend (726-1235 s on the 10 backend releases of 5 Nov),
# and the running backend keeps reading that checkout: 132 lazy imports of modules not loaded at the start, data files
# and every child process it starts. On 5 Nov the Phone summary answered 500 on every phone for that reason.
#
# Layout under BACKEND_TREES (default: <project>/../loupe-backend):
#   blue/, green/  git worktrees, detached, each at one commit. The live checkout's .env, data, evidence-data, backend/logs
#                  and deploy/logs are links, so a tree holds code only and nothing is lost when it moves.
#   current        symlink to the tree the backend starts from (the unit's WorkingDirectory, through a drop-in).
#
# A release stages the commit in the tree no backend process runs from, prepares and compiles there, and switches
# `current` right before it replaces the backend. The old backend keeps the tree it started in: a process's working
# directory stays where it is when the link moves, so its lazy imports, data files and children read its own commit.
# The live checkout still moves first: the release tooling, the gates, the migrations and the image builds use it. A
# failed release needs no undo here: until the switch nothing the backend reads has changed.
#
# Packages follow the same rule (lx-releasehold): <tree>/.venv links to venvs/<hash of backend/requirements.txt>, built
# beside by a hard-link copy of the venv in use plus pip, so a running backend never reads a package newer than its
# tree. pip never writes a file in place, so the copies share only files that did not change. The backend starts
# through current/.venv; the scripts in a venv's bin name that venv's own folder, so a running process holds the real
# folder whichever way the link moves. The checkout's .venv stays the release tooling's, brought up to date after a
# healthy release.
#
# Callers provide PROJECT_DIR, RUN_AS, SYSTEMCTL, VENV_DIR; the unit file helpers are in deploy/backend-socket.sh.
# Way back: "checkout" in deploy/backend-tree.conf; the next restart removes the drop-in.

# Run as a script (deploy-now.sh), the project is the one this file is in.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

BACKEND_TREES="${BACKEND_TREES:-$(cd "${PROJECT_DIR}/.." && pwd)/loupe-backend}"
BACKEND_TREE_DROPIN_NAME="70-lx-releaseprep-tree.conf"
BACKEND_TREE_SHARED=".env data evidence-data backend/logs deploy/logs"
BACKEND_TREE_UNIT="${BACKEND_UNIT:-owl-backend-v2}"
BACKEND_CGROUP_ROOT="${BACKEND_CGROUP_ROOT:-/sys/fs/cgroup}"
BACKEND_TREE_APPLIED=false
BACKEND_TREE_PREVIOUS=""
BACKEND_TREE_STAGED=""

backend_tree_wanted() {
    local wanted
    wanted="$(grep -v '^[[:space:]]*\(#\|$\)' "${PROJECT_DIR}/deploy/backend-tree.conf" 2>/dev/null | head -1 | tr -d '[:space:]' || true)"
    [ "${wanted}" = trees ] && echo trees || echo checkout
}

backend_tree_dropin() {
    echo "${BACKEND_SOCKET_UNIT_DIR:-/etc/systemd/system}/${BACKEND_TREE_UNIT}.service.d/${BACKEND_TREE_DROPIN_NAME}"
}

backend_tree_current() {
    basename "$(readlink "${BACKEND_TREES}/current" 2>/dev/null)" 2>/dev/null
}

# The trees a process of the unit has as its working directory, one per line: what the processes really do, whichever
# tree `current` names, children and a second backend during a handover included.
backend_tree_in_use() {
    local group path pid cwd
    group="$($SYSTEMCTL show -p ControlGroup --value "${BACKEND_TREE_UNIT}" 2>/dev/null)"
    [ -n "${group}" ] && [ -d "${BACKEND_CGROUP_ROOT}${group}" ] || return 0
    find "${BACKEND_CGROUP_ROOT}${group}" -name cgroup.procs 2>/dev/null | while read -r path; do
        while read -r pid; do
            cwd="$(readlink "/proc/${pid}/cwd" 2>/dev/null)" || continue
            case "${cwd}" in
                "$(readlink -f "${BACKEND_TREES}")"/*)
                    cwd="${cwd#"$(readlink -f "${BACKEND_TREES}")"/}"
                    echo "${cwd%%/*}" ;;
            esac
        done < "${path}"
    done | sort -u
}

# The tree a release may move: not the one `current` names, unless a failed release left that one unused, and never one a
# process runs from.
backend_tree_free() {
    local used current first second
    used="$(backend_tree_in_use)"
    current="$(backend_tree_current)"
    if [ "${current}" = blue ]; then first=green second=blue; else first=blue second=green; fi
    if ! echo "${used}" | grep -qx "${first}"; then
        echo "${first}"
    elif ! echo "${used}" | grep -qx "${second}"; then
        echo "${second}"
    else
        return 1
    fi
}

backend_tree_link_shared() {
    local tree="$1" path
    for path in ${BACKEND_TREE_SHARED}; do
        $RUN_AS mkdir -p "$(dirname "${tree}/${path}")"
        $RUN_AS ln -sfn "${PROJECT_DIR}/${path}" "${tree}/${path}"
    done
}

# The hash of <commit>'s package list, "none" when it has none.
backend_venv_hash() {
    (cd "${PROJECT_DIR}" && $RUN_AS git rev-parse --verify --quiet "$1:backend/requirements.txt" 2>/dev/null) || echo none
}

backend_venv_dir() {
    echo "${BACKEND_TREES}/venvs/$1"
}

# Hard-links the tree <source> as <dest>. The kernel refuses a hard link to a file the release user does not own
# (fs.protected_hardlinks=1): on 11 Nov 35 pytest caches a root test run left in the running venv on 9 Nov (mode 600,
# root) stopped every release that changed backend/requirements.txt. Such a file is copied when the release user can
# read it; a bytecode cache (__pycache__/*.pyc) it cannot read is left out, since Python rebuilds a missing cache. Any
# other error still fails.
backend_link_copy() {
    local source="$1" dest="$2" errors line from to copied=0 skipped=0
    errors="$($RUN_AS env LC_ALL=C cp -al "${source}" "${dest}" 2>&1 >/dev/null)" && return 0
    [ -n "${errors}" ] || return 1
    while IFS= read -r line; do
        case "${line}" in
            "cp: cannot create hard link '"*"' to '"*"': Operation not permitted") ;;
            *) printf '%s\n' "${line}" >&2; return 1 ;;
        esac
        to="${line#"cp: cannot create hard link '"}"; to="${to%%"' to '"*}"
        from="${line#*"' to '"}"; from="${from%"': Operation not permitted"}"
        [ ! -e "${to}" ] || { printf '%s\n' "${line}" >&2; return 1; }
        if $RUN_AS test -r "${from}"; then
            $RUN_AS cp --preserve=mode,timestamps -- "${from}" "${to}" || return 1
            copied=$((copied + 1))
        else
            case "${from}" in
                */__pycache__/*.pyc) skipped=$((skipped + 1)) ;;
                *) printf 'cannot read %s\n' "${from}" >&2; return 1 ;;
            esac
        fi
    done <<< "${errors}"
    echo "  venv copy: ${copied} file(s) of another user copied, ${skipped} unreadable bytecode cache(s) left out" >&2
}

# Builds venvs/<hash> beside the venv in use, unless it is complete already. Prints nothing; fails with the venv in use
# untouched. <requirements>: the list to install, from the tree being staged.
backend_venv_build() {
    local hash="$1" requirements="$2" dir source tmp file installed
    dir="$(backend_venv_dir "${hash}")"
    [ -e "${dir}/.loupe-venv" ] && return 0
    source="$(readlink -f "${BACKEND_TREES}/current/.venv" 2>/dev/null || true)"
    [ -d "${source}" ] || source="$(readlink -f "${VENV_DIR}")"
    tmp="${dir}.building"
    $RUN_AS mkdir -p "${BACKEND_TREES}/venvs" || return 1
    $RUN_AS rm -rf -- "${tmp}"
    backend_link_copy "${source}" "${tmp}" || { $RUN_AS rm -rf -- "${tmp}"; return 1; }
    installed="$(cat "${source}/.loupe-venv" 2>/dev/null || true)"
    if [ "${installed}" != "${hash}" ] && [ -f "${requirements}" ]; then
        if ! $(release_build_scope 2>/dev/null) $RUN_AS "${tmp}/bin/python" -m pip install -r "${requirements}" --quiet; then
            $RUN_AS rm -rf -- "${tmp}"
            return 1
        fi
    fi
    # sed -i writes a new file, so the copy it came from keeps its own folder names.
    for file in "${tmp}"/bin/* "${tmp}/pyvenv.cfg"; do
        [ -f "${file}" ] && [ ! -L "${file}" ] && grep -qIF -e "${source}" -e "${tmp}" "${file}" 2>/dev/null || continue
        $RUN_AS sed -i -e "s#${tmp}#${dir}#g" -e "s#${source}#${dir}#g" "${file}" || { $RUN_AS rm -rf -- "${tmp}"; return 1; }
    done
    $RUN_AS rm -f -- "${tmp}/.loupe-venv"
    $RUN_AS sh -c 'echo "$1" > "$2"' sh "${hash}" "${tmp}/.loupe-venv" || { $RUN_AS rm -rf -- "${tmp}"; return 1; }
    $RUN_AS rm -rf -- "${dir}"
    $RUN_AS mv -T -- "${tmp}" "${dir}"
}

# <tree name> <commit>: the tree's .venv is the venv of the commit's package list.
backend_venv_stage() {
    local tree="${BACKEND_TREES}/$1" hash
    hash="$(backend_venv_hash "$2")"
    backend_venv_build "${hash}" "${tree}/backend/requirements.txt" || return 1
    $RUN_AS ln -sfn "../venvs/${hash}" "${tree}/.venv.tmp" && $RUN_AS mv -Tf "${tree}/.venv.tmp" "${tree}/.venv"
}

# Removes every venv neither tree links to. A process started from one keeps both trees' links until its tree moves,
# and backend_tree_free never moves a tree in use.
backend_venv_prune() {
    local dir keep
    [ -d "${BACKEND_TREES}/venvs" ] || return 0
    keep="$(readlink -f "${BACKEND_TREES}/blue/.venv" "${BACKEND_TREES}/green/.venv" 2>/dev/null || true)"
    for dir in "${BACKEND_TREES}"/venvs/*; do
        [ -d "${dir}" ] || continue
        echo "${keep}" | grep -qxF "$(readlink -f "${dir}")" || $RUN_AS rm -rf -- "${dir}"
    done
}

# Puts <commit> in <tree>, which no backend process runs from. A tree keeps its compiled files, so only what the commit
# changed compiles again: a backend started from a tree with none takes 130 s to import at load 43, 21-26 s with them.
backend_tree_move() {
    local name="$1" commit="$2" tree="${BACKEND_TREES}/$1" at wanted
    wanted="$(cd "${PROJECT_DIR}" && $RUN_AS git rev-parse --verify --quiet "${commit}^{commit}" 2>/dev/null || echo "${commit}")"
    if [ ! -e "${tree}/.git" ]; then
        $RUN_AS mkdir -p "${BACKEND_TREES}" || return 1
        (cd "${PROJECT_DIR}" && $RUN_AS git worktree add --quiet --force --detach "${tree}" "${commit}") || return 1
    else
        at="$($RUN_AS git -C "${tree}" rev-parse HEAD 2>/dev/null || true)"
        if [ "${at}" != "${wanted}" ]; then
            # A prepare left running in this tree would read a mix of the two commits.
            systemctl stop loupe-financial-prepare 2>/dev/null || true
            $RUN_AS git -C "${tree}" checkout --quiet --force --detach "${commit}" || return 1
        fi
    fi
    backend_tree_link_shared "${tree}" || return 1
    backend_venv_stage "${name}" "${commit}" || return 1
    $(release_build_scope 2>/dev/null) $RUN_AS "${VENV_DIR}/bin/python" -m compileall -q -x '/(tests|benchmarks|scripts)/' \
        "${tree}/backend" >/dev/null || echo "  [WARN] Not every file of ${name} compiled; the backend compiles them at its start" >&2
}

# Moves a free tree to <commit>. Sets BACKEND_TREE_STAGED and, for the prepare, LOUPE_PREPARE_BACKEND_DIR. From here the
# release's tooling (gates, migrations) runs on the staged tree's packages.
backend_tree_stage() {
    local commit="$1" name
    if [ "$(backend_tree_wanted)" != trees ]; then
        BACKEND_TREE_STAGED=""
        LOUPE_PREPARE_BACKEND_DIR="${PROJECT_DIR}/backend"
        export LOUPE_PREPARE_BACKEND_DIR
        return 0
    fi
    if ! name="$(backend_tree_free)"; then
        echo "  [FAIL] Backend processes run from both trees: nothing can be moved under them" >&2
        return 1
    fi
    backend_tree_move "${name}" "${commit}" || return 1
    BACKEND_TREE_STAGED="${name}"
    VENV_DIR="$(readlink -f "${BACKEND_TREES}/${name}/.venv")"
    LOUPE_PREPARE_BACKEND_DIR="${BACKEND_TREES}/${name}/backend"
    export LOUPE_PREPARE_BACKEND_DIR
    # The running backend sees no new code on disk: this says its views are about to be replaced (view_warmup.py).
    $RUN_AS touch "${BACKEND_TREES}/.release-staged"
}

backend_tree_point() {  # <name>: `current` moves in one step
    $RUN_AS ln -sfn "$1" "${BACKEND_TREES}/.current.tmp" &&
        $RUN_AS mv -Tf "${BACKEND_TREES}/.current.tmp" "${BACKEND_TREES}/current"
}

backend_tree_remove_dropin() {
    local elevate=()
    [ "$(id -u)" -ne 0 ] && elevate=(sudo)
    [ -e "$(backend_tree_dropin)" ] || return 0
    "${elevate[@]}" rm -f -- "$(backend_tree_dropin)"
    $SYSTEMCTL daemon-reload
}

# Fails when the new tree is not in place; the caller must then leave the running backend alone.
# Right before the backend is replaced, stopped or not: with the port held a queued request can start the unit the
# moment the old one stops, and that start must already find the new tree.
backend_tree_apply() {
    local changed
    if [ "$(backend_tree_wanted)" != trees ]; then
        backend_tree_remove_dropin
        return 0
    fi
    [ -n "${BACKEND_TREE_STAGED}" ] || return 1
    BACKEND_TREE_PREVIOUS="$(backend_tree_current)"
    backend_tree_point "${BACKEND_TREE_STAGED}" || return 1
    $RUN_AS rm -f "${BACKEND_TREES}/.release-staged"
    BACKEND_TREE_APPLIED=true
    changed="$(backend_socket_install_file "$(backend_tree_dropin)" \
        "$(printf '# deploy/backend-tree.sh: the backend runs from a tree a release never moves under it.\n[Service]\nWorkingDirectory=%s/current/backend\nEnvironment="PATH=%s/current/.venv/bin:/usr/local/bin:/usr/bin:/bin"\n' "${BACKEND_TREES}" "${BACKEND_TREES}")")" || return 1
    [ -n "${changed}" ] && $SYSTEMCTL daemon-reload
    echo "  [  OK] The backend starts from ${BACKEND_TREE_STAGED} (was ${BACKEND_TREE_PREVIOUS:-the checkout})"
}

# Back to what ran before this release: the tree it ran from, at <commit>, or the checkout when it ran from there. A
# release that never reached backend_tree_apply changed nothing here. What this run did decides, not the switch file:
# the checkout has just gone back to a commit that may have none.
backend_tree_rollback() {
    local commit="$1"
    [ "${BACKEND_TREE_APPLIED}" = true ] || return 0
    BACKEND_TREE_APPLIED=false
    if [ -z "${BACKEND_TREE_PREVIOUS}" ]; then
        $RUN_AS rm -f "${BACKEND_TREES}/current"
        backend_tree_remove_dropin
        return 0
    fi
    if ! backend_tree_in_use | grep -qx "${BACKEND_TREE_PREVIOUS}"; then
        backend_tree_move "${BACKEND_TREE_PREVIOUS}" "${commit}" || return 1
    else
        # In use and older than the packages layout: the unit starts through this link.
        [ -e "${BACKEND_TREES}/${BACKEND_TREE_PREVIOUS}/.venv" ] || backend_venv_stage "${BACKEND_TREE_PREVIOUS}" "${commit}" || return 1
    fi
    backend_tree_point "${BACKEND_TREE_PREVIOUS}"
}

# A release that ended after the switch with the old backend still up: `current` names what runs, so a later start of
# the unit gets that code.
backend_tree_settle() {
    local used
    $RUN_AS rm -f "${BACKEND_TREES}/.release-staged"
    used="$(backend_tree_in_use)"
    if [ -n "${used}" ] && [ "$(echo "${used}" | wc -l)" -eq 1 ] && [ "${used}" != "$(backend_tree_current)" ]; then
        backend_tree_point "${used}"
    fi
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    # deploy-now.sh, as root, before the prepare: prints the backend folder the prepare runs from.
    set -euo pipefail
    VENV_DIR="${PROJECT_DIR}/.venv"
    if [ "$(id -u)" -eq 0 ]; then RUN_AS="sudo -u $(stat -c '%U' "${PROJECT_DIR}") -H"; SYSTEMCTL=systemctl; else RUN_AS=""; SYSTEMCTL="sudo systemctl"; fi
    # shellcheck source=deploy/frontend-release.sh
    source "${PROJECT_DIR}/deploy/frontend-release.sh"
    case "${1:-}" in
        stage) backend_tree_stage "$2" >&2; echo "${LOUPE_PREPARE_BACKEND_DIR}" ;;
        *) echo "usage: backend-tree.sh stage <commit>" >&2; exit 2 ;;
    esac
fi
