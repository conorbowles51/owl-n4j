#!/usr/bin/env bash
# One encrypted bundle of everything outside the repo that the app needs to come back: env file, nginx and systemd
# units, mount table, deploy key. Daily, kept with the backups, 30 days.
#
#   keys-bundle.sh init     create the passphrase file if it is missing (mode 600); prints only its path
#   keys-bundle.sh dump     write <BACKUP_DIR>/keys-YYYYMMDD-HHMMZ/{bundle.tar.gpg,files.tsv,meta.env}; reads it back
#   keys-bundle.sh check    exit 1 (and run BACKUP_ALERT_CMD) unless the newest set is under 25 h old and decrypts
#   keys-bundle.sh open <set> <dest dir>     decrypt a bundle into an empty directory (restore step)
#
# The bundle is AES-256 through gpg --symmetric. The passphrase lives only in KEYS_PASSPHRASE_FILE (root, mode 600)
# and in Neil's password manager: never in the repo, a command line, a log or a job message. A bundle on this box
# is no use if the box is gone and the passphrase went with it, so `init` is followed by Neil copying the file's
# contents off the box. files.tsv lists names, sizes and hashes of what went in; it holds no secret values.
#
# Install: see the header of deploy/owl-keys-bundle.service.
set -euo pipefail
umask 077
LOG_NAME=keys-bundle
BACKUP_DIR="${BACKUP_DIR:-/mnt/owl-data/backups/keys}"
. "$(dirname "${BASH_SOURCE[0]}")/backup-lib.sh"
KEYS_PASSPHRASE_FILE="${KEYS_PASSPHRASE_FILE:-/root/.config/loupe-backup/passphrase}"
GPG="${GPG:-gpg}"
# One path or glob per line. A path that matches nothing is listed in files.tsv as "missing"; the bundle is still
# written, with what is there, and the run and the check both alert.
KEYS_PATHS="${KEYS_PATHS:-${LIVE_CHECKOUT}/.env
/home/conorbowles51/.ssh/deploy_key
/home/conorbowles51/.ssh/config
/etc/fstab
/etc/nginx/nginx.conf
/etc/nginx/sites-available/*
/etc/default/owl-backend-allocator
/etc/docker/daemon.json
/etc/systemd/system/owl-*
/etc/systemd/system/loupe*
/etc/systemd/system/fin-watchdog*}"

# The public halves and the custody record come back with the rest. Listed only when there, so a box with no recovery key
# does not read as a short bundle. The private drill key is never bundled: a restored box makes its own.
for extra in recovery-public.asc recovery-custody drill-public.asc; do
    [[ ! -s "${SEAL_DIR:-/root/.config/loupe-backup}/${extra}" ]] || KEYS_PATHS+=$'\n'"${SEAL_DIR:-/root/.config/loupe-backup}/${extra}"
done

gpg_args=(--batch --yes --quiet --pinentry-mode loopback --passphrase-file "${KEYS_PASSPHRASE_FILE}")

do_init() {
    mkdir -p "$(dirname "${KEYS_PASSPHRASE_FILE}")"
    if [[ -s "${KEYS_PASSPHRASE_FILE}" ]]; then
        echo "passphrase file already there: ${KEYS_PASSPHRASE_FILE}"
        return 0
    fi
    ( umask 077; openssl rand -base64 36 > "${KEYS_PASSPHRASE_FILE}" )
    echo "passphrase written to ${KEYS_PASSPHRASE_FILE}; copy its contents to the password manager"
}

do_dump() {
    guard_exit
    mkdir -p "${BACKUP_DIR}"
    local previous name out list missing=0 entries p f
    previous="$(sets keys | tail -n 1)"
    name="keys-$(stamp)Z"
    if [[ ! -s "${KEYS_PASSPHRASE_FILE}" ]]; then
        alert "no keys bundle: passphrase file ${KEYS_PASSPHRASE_FILE} is missing; run keys-bundle.sh init; newest is ${previous:-none}"
        return 1
    fi
    rm -rf -- "${BACKUP_DIR}"/.keys-*.partial
    out="${BACKUP_DIR}/.${name}.partial"
    mkdir -p "${out}"
    list="${out}/.paths"
    : > "${out}/files.tsv"
    while IFS= read -r p; do
        [[ -n "${p}" ]] || continue
        local matched=0
        for f in ${p}; do    # the glob is the point
            if [[ -f "${f}" ]]; then
                printf '%s\n' "${f#/}" >> "${list}"
                printf '%s\t%s\t%s\n' "${f}" "$(stat -c %s "${f}")" "$(sha256sum "${f}" | cut -d' ' -f1)" >> "${out}/files.tsv"
                matched=1
            elif [[ -d "${f}" ]]; then
                find "${f}" -type f | while IFS= read -r g; do
                    printf '%s\n' "${g#/}" >> "${list}"
                    printf '%s\t%s\t%s\n' "${g}" "$(stat -c %s "${g}")" "$(sha256sum "${g}" | cut -d' ' -f1)" >> "${out}/files.tsv"
                done
                matched=1
            fi
        done
        if (( ! matched )); then printf '%s\tmissing\t-\n' "${p}" >> "${out}/files.tsv"; missing=$(( missing + 1 )); fi
    done <<< "${KEYS_PATHS}"
    if [[ ! -s "${list}" ]]; then
        rm -rf -- "${out}"
        alert "no keys bundle: none of the listed files exist; newest is ${previous:-none}"
        return 1
    fi
    if ! tar -C / -cf - -T "${list}" 2>/dev/null | "${GPG}" "${gpg_args[@]}" --symmetric --cipher-algo AES256 \
        --s2k-digest-algo SHA512 --output "${out}/bundle.tar.gpg"; then
        rm -rf -- "${out}"
        alert "no keys bundle: gpg failed; newest is ${previous:-none}"
        return 1
    fi
    entries="$(read_back "${out}/bundle.tar.gpg")" || entries=0
    if [[ "${entries}" -ne "$(wc -l < "${list}")" ]]; then
        rm -rf -- "${out}"
        alert "no keys bundle: the new bundle read back ${entries} of $(wc -l < "${list}") files (or none); discarded; newest is ${previous:-none}"
        return 1
    fi
    rm -f -- "${list}"
    write_meta "${out}/meta.env" "files=${entries}" "missing=${missing}"
    mv -f -- "${out}" "${BACKUP_DIR}/${name}"
    log "wrote ${name} (${entries} files, ${missing} listed paths absent)"
    prune_sets keys
    if (( missing )); then
        alert "keys bundle ${name} is short: $(awk -F'\t' '$2 == "missing" {print $1}' "${BACKUP_DIR}/${name}/files.tsv" | tr '\n' ' ')not found"
        return 1
    fi
}

read_back() { "${GPG}" "${gpg_args[@]}" --decrypt "$1" 2>/dev/null | tar -tf - 2>/dev/null | wc -l; }

do_check() {
    check_set_age keys "keys" || return 1
    if [[ ! -s "${KEYS_PASSPHRASE_FILE}" ]]; then
        alert "keys bundle ${NEWEST_SET}: the passphrase file is gone from this box"
        return 1
    fi
    if grep -q '^missing=[1-9]' "${BACKUP_DIR}/${NEWEST_SET}/meta.env"; then
        alert "newest keys bundle ${NEWEST_SET} is short: $(awk -F'\t' '$2 == "missing" {print $1}' "${BACKUP_DIR}/${NEWEST_SET}/files.tsv" | tr '\n' ' ')not found"
        return 1
    fi
    local n; n="$(read_back "${BACKUP_DIR}/${NEWEST_SET}/bundle.tar.gpg")" || n=0
    if [[ "${n}" -lt 1 ]]; then
        alert "newest keys bundle ${NEWEST_SET} does not decrypt"
        return 1
    fi
    log "ok: newest ${NEWEST_SET}, ${NEWEST_AGE_H} h old, ${n} files"
}

do_open() {  # <set> <empty dest dir>
    [[ -d "${3:-}" ]] || { echo "usage: $0 open <set name> <empty dest dir>" >&2; return 2; }
    [[ -z "$(ls -A "$3")" ]] || { echo "$3 is not empty" >&2; return 2; }
    "${GPG}" "${gpg_args[@]}" --decrypt "${BACKUP_DIR}/$2/bundle.tar.gpg" | tar -xf - -C "$3"
    echo "opened $2 into $3"
}

case "${1:-}" in
    init) do_init ;;
    dump) do_dump ;;
    check) do_check ;;
    open) do_open "$@" ;;
    *) echo "usage: $0 init|dump|check|open" >&2; exit 2 ;;
esac
