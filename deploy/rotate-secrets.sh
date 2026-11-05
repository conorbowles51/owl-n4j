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
# ROOT_DIR, RELEASE_COMMAND and PYTHON_BIN are overridable for tests.
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

rekey() {
    ( cd "${ROOT_DIR}/backend" && set -a && . "${ENV_FILE}" && set +a && "${PYTHON_BIN}" scripts/rekey_ai_credentials.py "$@" )
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

${RELEASE_COMMAND}

rekey --apply
echo "Done. Everyone signs in again once."
