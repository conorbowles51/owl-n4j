#!/usr/bin/env bash
# Install the host CPU/IO/memory policy (lx-hostpolicy, WS-A): the live service above the jobs fleet.
# Idempotent; reloads systemd only. Slice moves take effect at each unit's next restart (deploy-now); settings on
# units that stay put apply at the reload. Way back: deploy/hostpolicy/install.sh --remove
set -euo pipefail
src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dest="${HOSTPOLICY_UNIT_DIR:-/etc/systemd/system}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
if [ "${1:-}" = "--remove" ]; then
    rm -f -- "${dest}"/loupe.slice "${dest}"/loupe-live.slice "${dest}"/fleet.slice "${dest}"/*.d/50-lx-hostpolicy.conf
else
    for f in loupe.slice loupe-live.slice fleet.slice; do install -m 0644 "${src}/${f}" "${dest}/${f}"; done
    for d in "${src}"/*.d; do
        mkdir -p "${dest}/$(basename "${d}")"
        install -m 0644 "${d}/50-lx-hostpolicy.conf" "${dest}/$(basename "${d}")/50-lx-hostpolicy.conf"
    done
fi
${SYSTEMCTL} daemon-reload
