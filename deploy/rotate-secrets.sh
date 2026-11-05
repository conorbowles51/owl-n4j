#!/usr/bin/env bash
# Give a server its own secrets, and turn on the refusal to start without them.
#
#   sudo bash deploy/rotate-secrets.sh --check     nothing is written: what would change, and that stored keys read
#   sudo bash deploy/rotate-secrets.sh --apply
#
# --apply keeps a copy of .env, writes new values for each secret that is missing or shipped, plus LOUPE_ENV=production,
# releases (which restarts the backend and the document engine with them), then moves the stored AI credentials to the
# new key. No value is ever printed.
#
# What people see: everyone signed in is signed out once and signs in again. Scripts holding a token sign in again.
# Undo: put the kept copy back as .env and release again. Stored AI credentials moved in the last step are then
# unreadable, so keep AI_CREDENTIAL_ENCRYPTION_KEY_PREVIOUS set to the new key in that case.
#
# ROOT_DIR, RELEASE_COMMAND, KEY_CHECK_COMMAND and PYTHON_BIN are overridable for tests.
set -euo pipefail

MODE="${1:---check}"
ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="${ROOT_DIR}/.env"
RELEASE_COMMAND="${RELEASE_COMMAND:-bash /mnt/owl-data/fin-wt/deploy-now.sh}"
PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"
SHIPPED_AI_KEY="loupe-development-ai-credentials-change-me"

[ -f "${ENV_FILE}" ] || { echo "Missing ${ENV_FILE}" >&2; exit 2; }
case "${MODE}" in --check|--apply) ;; *) echo "Use --check or --apply" >&2; exit 2 ;; esac

value_of() { sed -n "s/^$1=//p" "${ENV_FILE}" | tail -1 | sed -e 's/^["'\'']//' -e 's/["'\'']$//'; }

# Prints the names secret_check would refuse, one a line.
unusable() {
    ( cd "${ROOT_DIR}/backend" && set -a && . "${ENV_FILE}" && set +a && "${PYTHON_BIN}" -I -c '
import os, sys
sys.path.insert(0, os.getcwd())
import secret_check
for line in secret_check.problems(os.environ):
    print(line.split(" ", 1)[0])
' )
}

# Run as development: a new server's .env is still placeholders here, and config would refuse them.
rekey() {
    ( cd "${ROOT_DIR}/backend" && set -a && . "${ENV_FILE}" && set +a && LOUPE_ENV=development \
        "${PYTHON_BIN}" scripts/rekey_ai_credentials.py "$@" )
}

# Exit 0 only when the backend and every engine container hold the key now in .env. A release can answer success and
# leave them running (nothing to do for the code, or the engine busy), and credentials moved then would be unreadable.
new_key_is_running() {
    local want pid containers name
    want="$(value_of AI_CREDENTIAL_ENCRYPTION_KEY)"
    pid="$(systemctl show -p MainPID --value owl-backend-v2)"
    [ -n "${pid}" ] && [ "${pid}" != 0 ] || return 1
    tr '\0' '\n' < "/proc/${pid}/environ" | grep -Fxq "AI_CREDENTIAL_ENCRYPTION_KEY=${want}" || return 1
    containers="$(docker ps --format '{{.Names}}' | grep '^owl-v2-evidence' || true)"
    [ -n "${containers}" ] || return 1
    for name in ${containers}; do
        docker inspect "${name}" --format '{{range .Config.Env}}{{println .}}{{end}}' \
            | grep -Fxq "AI_CREDENTIAL_ENCRYPTION_KEY=${want}" || return 1
    done
}

NAMES="$(unusable)"
echo "Secrets to replace: ${NAMES:-none}" | tr '\n' ' '; echo
echo "LOUPE_ENV now: $(value_of LOUPE_ENV | grep . || echo unset)"
rekey

if [ "${MODE}" = "--check" ]; then
    echo "Nothing written."
    exit 0
fi

COPY="${ENV_FILE}.before-secrets-$(date -u +%Y%m%dT%H%M%SZ)"
cp -p "${ENV_FILE}" "${COPY}"
chmod 600 "${COPY}"

NEW="$(mktemp "${ENV_FILE}.new.XXXXXX")"
trap 'rm -f "${NEW}"' EXIT
cp -p "${ENV_FILE}" "${NEW}"
OLD_AI_KEY="$(value_of AI_CREDENTIAL_ENCRYPTION_KEY)"
set_line() {  # replaces any line for the name
    grep -v "^$1=" "${NEW}" > "${NEW}.x" || true
    cat "${NEW}.x" > "${NEW}"; rm -f "${NEW}.x"
    printf '%s=%s\n' "$1" "$2" >> "${NEW}"
}
for name in ${NAMES}; do
    set_line "${name}" "$("${PYTHON_BIN}" -I -c 'import secrets; print(secrets.token_urlsafe(48))')"
done
if printf '%s\n' ${NAMES} | grep -qx AI_CREDENTIAL_ENCRYPTION_KEY; then
    set_line AI_CREDENTIAL_ENCRYPTION_KEY_PREVIOUS "${OLD_AI_KEY:-${SHIPPED_AI_KEY}}"
fi
set_line LOUPE_ENV production
chmod 640 "${NEW}"
mv -f "${NEW}" "${ENV_FILE}"
trap - EXIT
echo "Written. The old file is kept as ${COPY}. Releasing."

STOPPED="Stored AI credentials were not moved and still work. Run --apply again once the release has gone out: it keeps the new values and finishes."
if ! ${RELEASE_COMMAND}; then
    echo "The release did not go out (see deploy-now.log). ${STOPPED}" >&2
    exit 1
fi
if ! ${KEY_CHECK_COMMAND:-new_key_is_running}; then
    echo "The release answered, but the backend or the document engine is not running the new key yet. ${STOPPED}" >&2
    exit 1
fi

rekey --apply
echo "Done. Everyone signs in again once."
