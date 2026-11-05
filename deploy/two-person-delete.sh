#!/usr/bin/env bash
# Deleting a backup early takes two named people. Retention (backup-expiry.sh) needs no approval; this is for anything
# sooner, or anything with no retention rule.
#
#   two-person-delete.sh request <name> --by <person> --reason "<why>"   name: a set, a dump, a suspect one, or a hand-made dump
#   two-person-delete.sh request-case <case id> --by <person> --reason "<why>"
#   two-person-delete.sh approve <request id> --by <another person>
#   two-person-delete.sh execute <request id>
#   two-person-delete.sh list
#
# A case's deletion is done in the app, by the person who approved it; execute records that and deletes nothing. The app
# itself takes one person to delete a case. The newest set of a store cannot be deleted, so a store is never left with no
# backup. An approval lapses after REQUEST_DAYS (7). Every step is a line in <BACKUP_ROOT>/deletions/log.tsv, holding
# names, never contents.
#
# The names are typed by whoever is at the keyboard. This keeps two people's decision on record; it does not stop root.
set -uo pipefail
umask 077
LOG_NAME=two-person-delete
. "$(dirname "${BASH_SOURCE[0]}")/backup-lib.sh"
BACKUP_ROOT="${BACKUP_ROOT:-/mnt/owl-data/backups}"
BOOK="${BACKUP_ROOT}/deletions"
REQUEST_DAYS="${REQUEST_DAYS:-7}"

die() { echo "REFUSED: $*" >&2; exit 1; }
entry() { mkdir -p "${BOOK}"; printf '%s\t%s\n' "$(date -u -d "@$(now)" +%FT%TZ)" "$*" >> "${BOOK}/log.tsv"; }
field() { sed -n "s/^$2=//p" "${BOOK}/requests/$1" | head -n 1; }
same_person() { [[ "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | xargs)" == "$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]' | xargs)" ]]; }

locate() {  # <name>: sets TARGET_STORE, TARGET_PATH. Only names the backup scripts themselves write, or a hand-made dump
    local name="$1"
    case "${name}" in
        */*|..*) die "a name, not a path: ${name}" ;;
        .owl_db-*.suspect) TARGET_STORE=scheduled ;;
        .neo4j-*.suspect) TARGET_STORE=neo4j ;;
        .chroma-*.suspect) TARGET_STORE=chroma ;;
        .*) die "a name, not a path: ${name}" ;;
        owl_db-[0-9]*Z.dump) TARGET_STORE=scheduled ;;
        neo4j-[0-9]*Z) TARGET_STORE=neo4j ;;
        chroma-[0-9]*Z) TARGET_STORE=chroma ;;
        keys-[0-9]*Z) TARGET_STORE=keys ;;
        *.dump) TARGET_STORE=""
            [[ ! -e "${HAND_DUMPS:-/mnt/owl-data/db-backups}/${name}" ]] || HAND_PATH="${HAND_DUMPS:-/mnt/owl-data/db-backups}/${name}" ;;
        *) die "not a backup this tool knows: ${name}" ;;
    esac
    TARGET_PATH="${HAND_PATH:-${BACKUP_ROOT}/${TARGET_STORE:+${TARGET_STORE}/}${name}}"
    [[ -e "${TARGET_PATH}" || -e "${TARGET_PATH}.gpg" ]] || die "no such backup: ${name}"
}

newest_of() {  # <store>
    case "$1" in
        scheduled) find "${BACKUP_ROOT}/scheduled" -maxdepth 1 -type f \( -name 'owl_db-[0-9]*Z.dump' -o -name 'owl_db-[0-9]*Z.dump.gpg' \) -printf '%f\n' | sed 's/\.gpg$//' | sort -u | tail -n 1 ;;
        *) BACKUP_DIR="${BACKUP_ROOT}/$1" sets "$1" | tail -n 1 ;;
    esac
}

do_request() {  # <kind> <target> --by <person> --reason <why>
    local kind="$1" target="$2" by="" reason="" id; shift 2
    while (( $# )); do
        case "$1" in --by) by="${2:-}"; shift 2 ;; --reason) reason="${2:-}"; shift 2 ;; *) die "unknown argument $1" ;; esac
    done
    [[ -n "${by}" && -n "${reason}" ]] || die "--by and --reason are required"
    if [[ "${kind}" == backup ]]; then locate "${target}"; else
        [[ "${target}" =~ ^[0-9a-fA-F-]{8,36}$ ]] || die "not a case id: ${target}"
    fi
    id="del-$(date -u -d "@$(now)" +%Y%m%d-%H%M%S)-$RANDOM"
    mkdir -p "${BOOK}/requests"
    printf 'kind=%s\ntarget=%s\nby=%s\nreason=%s\nat=%s\n' "${kind}" "${target}" "${by}" "${reason//$'\n'/ }" "$(now)" > "${BOOK}/requests/${id}"
    entry "${id}	requested	${kind}	${target}	${by}	${reason//$'\n'/ }"
    echo "${id}"
}

need_request() {
    [[ "$1" =~ ^del-[0-9-]+$ && -f "${BOOK}/requests/$1" ]] || die "no such request: $1"
    [[ -z "$(field "$1" done)" ]] || die "$1 has already been carried out"
    (( $(now) - $(field "$1" at) < REQUEST_DAYS * 86400 )) || die "$1 is over ${REQUEST_DAYS} days old; ask again"
}

do_approve() {  # <id> --by <person>
    local id="$1" by=""
    need_request "${id}"
    [[ "${2:-}" == --by && -n "${3:-}" ]] || die "--by is required"
    by="$3"
    same_person "${by}" "$(field "${id}" by)" && die "the person who asked cannot approve: it takes two people"
    printf 'approved_by=%s\n' "${by}" >> "${BOOK}/requests/${id}"
    entry "${id}	approved	$(field "${id}" kind)	$(field "${id}" target)	${by}"
    echo "approved ${id}"
}

do_execute() {  # <id>
    local id="$1" kind target approver
    need_request "${id}"
    approver="$(field "${id}" approved_by)"
    [[ -n "${approver}" ]] || die "${id} has not been approved by a second person"
    kind="$(field "${id}" kind)"; target="$(field "${id}" target)"
    if [[ "${kind}" == case ]]; then
        printf 'done=%s\n' "$(now)" >> "${BOOK}/requests/${id}"
        entry "${id}	released	case	${target}	${approver}"
        echo "recorded. ${approver} now deletes case ${target} in the app; its activity log records the delete."
        return
    fi
    locate "${target}"
    if [[ -n "${TARGET_STORE}" && "$(newest_of "${TARGET_STORE}")" == "${target}" ]]; then
        die "${target} is the newest of its store; take a newer one first"
    fi
    if [[ -d "${TARGET_PATH}" ]]; then
        rm -rf -- "${TARGET_PATH}"
    else
        rm -f -- "${TARGET_PATH}" "${TARGET_PATH}.gpg" "${TARGET_PATH}.gpg.sha256" "${TARGET_PATH%.dump}.counts.tsv" "${TARGET_PATH%.dump}.meta"
    fi
    printf 'done=%s\n' "$(now)" >> "${BOOK}/requests/${id}"
    entry "${id}	deleted	backup	${target}	${approver}"
    echo "deleted ${target}"
}

do_list() {
    local f id
    for f in "${BOOK}"/requests/del-*; do
        [[ -f "${f}" ]] || continue
        id="$(basename "${f}")"
        printf '%s\t%s\t%s\tasked by %s\tapproved by %s\tdone %s\n' "${id}" "$(field "${id}" kind)" "$(field "${id}" target)" \
            "$(field "${id}" by)" "$(field "${id}" approved_by)" "$(field "${id}" done)"
    done
}

case "${1:-}" in
    request) shift; [[ -n "${1:-}" ]] || die "name the backup"; do_request backup "$@" ;;
    request-case) shift; [[ -n "${1:-}" ]] || die "name the case"; do_request case "$@" ;;
    approve) shift; do_approve "$@" ;;
    execute) shift; do_execute "${1:-}" ;;
    list) do_list ;;
    *) echo "usage: $0 request <name>|request-case <case id> --by <person> --reason <why>; approve <id> --by <person>; execute <id>; list" >&2; exit 2 ;;
esac
