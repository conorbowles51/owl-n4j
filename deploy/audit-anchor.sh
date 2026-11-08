#!/usr/bin/env bash
# Installs, enables or disables the daily audit-chain time-stamp from deploy/audit-anchor.conf (on|off).
# Called by deploy.sh after a healthy release; a failure here warns and never undoes a release.
# Usage: audit-anchor.sh install
set -u
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
UNIT_DIR="${AUDIT_ANCHOR_UNIT_DIR:-/etc/systemd/system}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
UNIT=owl-audit-anchor
AUDIT_ANCHOR_OUTPUT="${AUDIT_ANCHOR_OUTPUT:-/mnt/owl-data/audit-anchors}"

audit_anchor_wanted() {
    local wanted
    wanted="$(grep -v '^[[:space:]]*\(#\|$\)' "${PROJECT_DIR}/deploy/audit-anchor.conf" 2>/dev/null | head -1 | tr -d '[:space:]')"
    [ "${wanted}" = on ] && echo on || echo off
}

install_units() {
    local changed="" name
    for name in "${UNIT}.service" "${UNIT}.timer"; do
        if ! cmp -s "${PROJECT_DIR}/deploy/${name}" "${UNIT_DIR}/${name}"; then
            install -m 0644 "${PROJECT_DIR}/deploy/${name}" "${UNIT_DIR}/${name}" || return 1
            changed=1
        fi
    done
    [ -z "${changed}" ] || $SYSTEMCTL daemon-reload || return 1
    mkdir -p "${AUDIT_ANCHOR_OUTPUT}" && chmod 0700 "${AUDIT_ANCHOR_OUTPUT}"
    $SYSTEMCTL enable --now "${UNIT}.timer"
}

case "${1:-}" in
    install)
        if [ "$(audit_anchor_wanted)" = on ]; then
            install_units && echo "audit anchor: daily time-stamp enabled (${UNIT}.timer)"
        elif [ -e "${UNIT_DIR}/${UNIT}.timer" ]; then
            $SYSTEMCTL disable --now "${UNIT}.timer" && echo "audit anchor: off; timer disabled, stamps kept"
        else
            echo "audit anchor: off"
        fi
        ;;
    *) echo "usage: $0 install" >&2; exit 64 ;;
esac
