#!/usr/bin/env bash
# When data leaves the backups. Nothing here deletes: expiry is done by each dump script's retention, on its next run.
#
#   backup-expiry.sh report                       each store: sets held, oldest, newest, retention, and files with no expiry
#   backup-expiry.sh report --removed-on YYYY-MM-DD   also the day data removed from the app that day is out of every set
#
# A set holds every case, so a case cannot be cut out of one: data removed from the app stays in the sets taken before
# the removal until they age out. A file with no retention rule (a hand-made dump) never expires by itself; it is listed
# so a person decides, through deploy/two-person-delete.sh. A dump set aside as .suspect (under half the size of the one
# before) has no retention and is not sealed either. Retention days are read from the units' defaults below.
set -uo pipefail
LOG_NAME=backup-expiry
. "$(dirname "${BASH_SOURCE[0]}")/backup-lib.sh"
BACKUP_ROOT="${BACKUP_ROOT:-/mnt/owl-data/backups}"
KEEP_PG="${KEEP_PG:-30}"; KEEP_NEO4J="${KEEP_NEO4J:-30}"; KEEP_CHROMA="${KEEP_CHROMA:-14}"; KEEP_KEYS="${KEEP_KEYS:-30}"
removed_on=""
last_out=0

names() {  # <store>: its set or dump names, oldest first, as YYYYMMDD-HHMM
    case "$1" in
        postgres) find "${BACKUP_ROOT}/scheduled" -maxdepth 1 -type f \( -name 'owl_db-[0-9]*Z.dump' -o -name 'owl_db-[0-9]*Z.dump.gpg' \) -printf '%f\n' 2>/dev/null | sed 's/\.gpg$//; s/^owl_db-//; s/Z\.dump$//' ;;
        *) find "${BACKUP_ROOT}/$1" -mindepth 1 -maxdepth 1 -type d -not -name '.*' -printf '%f\n' 2>/dev/null | sed 's/^[a-z0-9]*-//; s/Z$//' ;;
    esac | sort -u
}

name_epoch() { date -u -d "${1:0:8} ${1:9:2}:${1:11:2}" +%s; }

one() {  # <store> <keep days> [holds data: yes|no]
    local store="$1" keep="$2" n first last line before="" t
    mapfile -t all < <(names "${store}")
    n="${#all[@]}"
    if (( n == 0 )); then printf '%s: no sets\n' "${store}"; return; fi
    first="${all[0]}"; last="${all[n-1]}"
    printf '%s: %s sets, oldest %s, newest %s, kept %s days\n' "${store}" "${n}" "${first}" "${last}" "${keep}"
    [[ -n "${removed_on}" && "${3:-yes}" == yes ]] || return
    for line in "${all[@]}"; do [[ "${line:0:8}" > "${removed_on//-/}" ]] || before="${line}"; done
    if [[ -z "${before}" ]]; then
        printf '  no set of this store was taken on or before %s\n' "${removed_on}"
        return
    fi
    # Pruned by the first nightly run after the set is more than <keep> days old. Holds only while newer sets exist.
    t=$(( $(name_epoch "${before}") + (keep + 1) * 86400 ))
    printf '  newest set that can hold it: %s; out by %s\n' "${before}" "$(date -u -d "@${t}" +%F)"
    (( t > last_out )) && last_out="${t}"
}

if [[ "${1:-}" != report ]]; then echo "usage: $0 report [--removed-on YYYY-MM-DD]" >&2; exit 2; fi
if [[ "${2:-}" == --removed-on ]]; then
    removed_on="${3:-}"
    [[ "${removed_on}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] && date -u -d "${removed_on}" +%s >/dev/null 2>&1 || { echo "bad date: ${removed_on}" >&2; exit 2; }
fi
one postgres "${KEEP_PG}"
one neo4j "${KEEP_NEO4J}"
one chroma "${KEEP_CHROMA}"
one keys "${KEEP_KEYS}" no
if [[ -n "${removed_on}" ]]; then
    if (( last_out )); then echo "out of every set by: $(date -u -d "@${last_out}" +%F)"; else echo "out of every set: no set holds it"; fi
fi
held="$(find "${BACKUP_ROOT}" "${HAND_DUMPS:-/mnt/owl-data/db-backups}" -maxdepth 1 -type f \( -name '*.dump' -o -name '*.dump.gpg' \) -printf '%p\n' 2>/dev/null | sort)"
held+=$'\n'"$(find "${BACKUP_ROOT}" -mindepth 2 -maxdepth 2 -name '.*.suspect' -printf '%p\n' 2>/dev/null | sort)"
held="$(grep . <<<"${held}" || true)"
if [[ -n "${held}" ]]; then
    echo "no expiry, a person decides (hand-made dumps, and dumps set aside as suspect):"
    printf '  %s\n' ${held}
fi
if [[ -n "${EVIDENCE_COPY_DEST:-}" ]]; then
    echo "evidence copy: keeps files removed at source, and every earlier version under superseded/, with no expiry"
fi
