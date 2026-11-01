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
    # The settings applied to running units below live under /run until reboot and override the slice files: remove
    # them too, or the way back leaves the floors and weights in force.
    control="${HOSTPOLICY_CONTROL_DIR:-/run/systemd/system.control}"
    for u in loupe.slice loupe-live.slice fleet.slice $(cd "${src}" && ls -d -- *.d | sed 's/\.d$//'); do
        for k in CPUWeight IOWeight MemoryLow MemoryMin MemoryHigh MemorySwapMax; do rm -f -- "${control}/${u}.d/50-${k}.conf"; done
    done
else
    for f in loupe.slice loupe-live.slice fleet.slice; do install -m 0644 "${src}/${f}" "${dest}/${f}"; done
    for d in "${src}"/*.d; do
        mkdir -p "${dest}/$(basename "${d}")"
        install -m 0644 "${d}/50-lx-hostpolicy.conf" "${dest}/$(basename "${d}")/50-lx-hostpolicy.conf"
    done
fi
${SYSTEMCTL} daemon-reload
# daemon-reload does not push new memory floors or caps into the cgroups of units already running (1 Nov: a new
# MemoryMin stayed 0 on the running backend and both slices after the reload). Apply the resource settings to the
# running units too. --runtime writes under /run (gone at reboot, removed by --remove); for the three slices those
# copies take precedence over the files until reboot, so change a slice by editing its file and rerunning this.
if [ "${1:-}" != "--remove" ]; then
    apply_running() {  # <unit> <file>
        local props
        props=$(grep -E '^(CPUWeight|IOWeight|MemoryLow|MemoryMin|MemoryHigh|MemorySwapMax)=' "$2" | tr '\n' ' ' || true)
        [ -n "${props}" ] || return 0
        ${SYSTEMCTL} is-active --quiet "$1" || return 0
        # shellcheck disable=SC2086
        ${SYSTEMCTL} set-property --runtime "$1" ${props} || echo "hostpolicy: could not apply ${props}to $1" >&2
    }
    for f in loupe.slice loupe-live.slice fleet.slice; do apply_running "${f}" "${src}/${f}"; done
    for d in "${src}"/*.d; do apply_running "$(basename "${d}" .d)" "${d}/50-lx-hostpolicy.conf"; done
fi
