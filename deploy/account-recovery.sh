#!/usr/bin/env bash
# Account recovery on the box, for when no administrator can sign in.
#
#   sudo bash deploy/account-recovery.sh reset <email>                     a reset code for an administrator
#   sudo bash deploy/account-recovery.sh reset <email> --remove-two-step   and clear a lost authenticator
#   sudo bash deploy/account-recovery.sh require --check                   who has enrolled; nothing is written
#   sudo bash deploy/account-recovery.sh require --on                      refused until every administrator is ready
#   sudo bash deploy/account-recovery.sh require --off
#   sudo bash deploy/account-recovery.sh rekey                             stored secrets move to MFA_ENCRYPTION_KEY
#
# A code is printed to this terminal once and is written nowhere else; every use is in the activity trail.
# ROOT_DIR and PYTHON_BIN are overridable for tests.
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"

cd "${ROOT_DIR}/backend"
exec "${PYTHON_BIN}" -m services.account_recovery "$@"
