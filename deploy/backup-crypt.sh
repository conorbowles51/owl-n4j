#!/usr/bin/env bash
# Encryption at rest for the recovery sets: each dump is sealed to a public key on this box, and the private key that
# opens it is kept off the box.
#
#   backup-crypt.sh new-key            make the recovery key: the public half stays here, the private half is shown once
#                                      and never written to disk; then, at a terminal, goes on to confirm-key
#   backup-crypt.sh confirm-key        read the saved private key on stdin, prove it opens a test message sealed to the
#                                      public key, and only then record custody
#   backup-crypt.sh new-drill-key      a second key, kept on this box, so the weekly restore drill can open sets
#   backup-crypt.sh status             what state the keys are in, and plain and sealed files per store
#   backup-crypt.sh seal-file <file>   seal one file, for a hand-made dump; plain removed once custody is confirmed
#   backup-crypt.sh open <file.gpg> <private key file>     write the plain file to stdout (restore step)
#
# Three states, from the files in SEAL_DIR (/root/.config/loupe-backup):
#   none         no public key. Sets are written plain, as before this script.
#   unconfirmed  public key here, custody not proven. Sets are written plain AND sealed. A lost key must not lose a
#                backup, so nothing plain is removed in this state.
#   confirmed    recovery-custody names this public key's fingerprint. Sets are sealed and the plain file removed; each
#                nightly run also seals what was written plain before custody.
#
# gpg, AES-256 to a Curve25519 key, no compression (the dumps are compressed or are vectors, which do not compress).
# X.gpg.sha256 beside each sealed file is the hash of the ciphertext, so `sha256sum -c` proves a copy with no key.
# Counts and meta files stay plain: they hold counts per case id and commits, and the hourly check reads them.
# While a dump is being verified it is plain on disk under a .partial name; a sealed set has no plain file afterwards.
# The sourcing script provides log and alert (backup-lib.sh).
SEAL_DIR="${SEAL_DIR:-/root/.config/loupe-backup}"
SEAL_PUBLIC="${SEAL_PUBLIC:-${SEAL_DIR}/recovery-public.asc}"
SEAL_CUSTODY="${SEAL_CUSTODY:-${SEAL_DIR}/recovery-custody}"
SEAL_DRILL_PUBLIC="${SEAL_DRILL_PUBLIC:-${SEAL_DIR}/drill-public.asc}"
SEAL_DRILL_PRIVATE="${SEAL_DRILL_PRIVATE:-${SEAL_DIR}/drill-private.asc}"
SEAL_SHM="${SEAL_SHM:-/dev/shm}"   # private keys are only ever handled in memory
GPG="${GPG:-gpg}"

seal_fingerprint() {  # <public key file>
    "${GPG}" --homedir "$2" --batch --no-tty --show-keys --with-colons "$1" 2>/dev/null | awk -F: '$1 == "fpr" {print $10; exit}'
}

seal_subkeys() {  # <public key file> <gpg home>: the long ids of its encryption keys
    "${GPG}" --homedir "$2" --batch --no-tty --show-keys --with-colons "$1" 2>/dev/null | awk -F: '($1 == "sub" || $1 == "pub") && $12 ~ /e/ {print $5}'
}

seal_tmp_home() {
    local home
    home="$(mktemp -d "${SEAL_SHM}/loupe-seal.XXXXXX")" || return 1
    printf '%s\n' "${home}"
}

seal_drop_home() {  # <home>
    "${GPGCONF:-gpgconf}" --homedir "$1" --kill all >/dev/null 2>&1 || true
    rm -rf -- "$1"
}

seal_state() {
    [[ -s "${SEAL_PUBLIC}" ]] || { echo none; return 0; }
    local home fpr
    home="$(seal_tmp_home)" || { echo unconfirmed; return 0; }
    fpr="$(seal_fingerprint "${SEAL_PUBLIC}" "${home}")"
    seal_drop_home "${home}"
    if [[ -n "${fpr}" && -s "${SEAL_CUSTODY}" ]] && grep -qx "fingerprint=${fpr}" "${SEAL_CUSTODY}"; then
        echo confirmed
    else
        echo unconfirmed
    fi
}

seal_check() {  # <file.gpg>: whole on disk as far as can be told without a key, and sealed to the recovery key
    local f="$1" home ids want rc=1 id
    [[ -s "${f}" && -s "${f}.sha256" && -s "${SEAL_PUBLIC}" ]] || return 1
    home="$(seal_tmp_home)" || return 1
    ids="$(head -c 8192 "${f}" | "${GPG}" --homedir "${home}" --batch --no-tty --list-packets 2>/dev/null |
        sed -n 's/.*keyid \([0-9A-Fa-f]\{16\}\).*/\1/p' | tr 'a-f' 'A-F')" || true
    want="$(seal_subkeys "${SEAL_PUBLIC}" "${home}")"
    for id in ${want}; do grep -qx "${id}" <<<"${ids}" && rc=0; done
    seal_drop_home "${home}"
    return "${rc}"
}

seal_hash_ok() {  # <file.gpg>: the ciphertext is the one that was written. Reads the whole file; the drill's check
    ( cd "$(dirname "$1")" && sha256sum -c --quiet --status "$(basename "$1").sha256" )
}

seal_file() {  # <plain file>: writes <file>.gpg and <file>.gpg.sha256 beside it; the plain file is left alone
    local f="$1" dir base tmp sum home rc=0 plain_size sealed_size
    local -a to=(--recipient-file "${SEAL_PUBLIC}")
    [[ -s "${SEAL_DRILL_PUBLIC}" ]] && to+=(--recipient-file "${SEAL_DRILL_PUBLIC}")
    dir="$(dirname "${f}")"; base="$(basename "${f}")"
    tmp="${dir}/.${base}.gpg.partial"
    home="$(seal_tmp_home)" || return 1
    sum="$( { "${GPG}" --homedir "${home}" --batch --quiet --no-tty --trust-model always --compress-algo none \
        --cipher-algo AES256 "${to[@]}" --output - --encrypt "${f}" || echo failed >&3; } 3>"${tmp}.rc" |
        tee "${tmp}" | sha256sum | cut -d' ' -f1)" || rc=1
    [[ -s "${tmp}.rc" ]] && rc=1
    rm -f -- "${tmp}.rc"
    seal_drop_home "${home}"
    plain_size="$(stat -c %s "${f}")"; sealed_size="$(stat -c %s "${tmp}" 2>/dev/null || echo 0)"
    if (( rc != 0 || sealed_size <= plain_size )); then
        rm -f -- "${tmp}"
        return 1
    fi
    mv -f -- "${tmp}" "${f}.gpg"
    printf '%s  %s\n' "${sum}" "${base}.gpg" > "${f}.gpg.sha256"
    seal_check "${f}.gpg" || { rm -f -- "${f}.gpg" "${f}.gpg.sha256"; return 1; }
}

seal_one() {  # <plain file>: seal by the state. A failure alerts and keeps the plain file: the backup itself stands
    local state; state="$(seal_state)"
    [[ "${state}" != none ]] || return 0
    if ! seal_file "$1"; then
        alert "$(basename "$1") could not be encrypted; the plain file stays"
        return 0
    fi
    [[ "${state}" == confirmed ]] || return 0
    # Read back from the disk before the only other copy goes.
    if seal_hash_ok "$1.gpg"; then rm -f -- "$1"; else alert "$(basename "$1").gpg does not read back; the plain file stays"; fi
}

seal_pending() {  # <dir> <depth> <name glob>...: once custody is confirmed, files left plain are sealed and removed
    local dir="$1" depth="$2" f; shift 2
    [[ "$(seal_state)" == confirmed ]] || return 0
    local -a names=(); local g
    for g in "$@"; do names+=(${names[@]:+-o} -name "${g}"); done
    while IFS= read -r -d '' f; do
        if seal_check "${f}.gpg" && seal_hash_ok "${f}.gpg"; then rm -f -- "${f}"; else seal_one "${f}"; fi
    done < <(find "${dir}" -mindepth 1 -maxdepth "${depth}" -type f \( "${names[@]}" \) -not -path '*/.*' -print0 2>/dev/null)
}

stored_size() {  # <plain path>: bytes of the plain file or, where only that exists, its sealed file; 0 when neither
    stat -c %s "$1" 2>/dev/null || stat -c %s "$1.gpg" 2>/dev/null || echo 0
}

open_begin() {  # <private key file>: sets OPEN_HOME, a keyring in memory for open_file
    OPEN_HOME="$(seal_tmp_home)" || return 1
    "${GPG}" --homedir "${OPEN_HOME}" --batch --quiet --no-tty --import "$1" >/dev/null 2>&1 || { open_end; return 1; }
}

open_file() {  # <file.gpg>: the plain bytes on stdout; a tampered or cut file fails the pipe (the cipher's own check)
    "${GPG}" --homedir "${OPEN_HOME}" --batch --quiet --no-tty --pinentry-mode loopback --passphrase '' --output - --decrypt "$1"
}

open_end() {
    [[ -z "${OPEN_HOME:-}" ]] || seal_drop_home "${OPEN_HOME}"
    OPEN_HOME=""
}

# --- commands -------------------------------------------------------------------------------------------------------

generate_key() {  # <name> <home>: a key with no passphrase of its own; the place it is kept is what protects it
    "${GPG}" --homedir "$2" --batch --quiet --no-tty --passphrase '' --quick-generate-key "$1" future-default default never 2>/dev/null
}

do_new_key() {
    if [[ -s "${SEAL_PUBLIC}" ]]; then
        echo "a recovery key is already here (${SEAL_PUBLIC}); sets sealed to it need its private key." >&2
        echo "To change keys, move that file aside first, knowing older sets stay sealed to the old key." >&2
        return 1
    fi
    mkdir -p "${SEAL_DIR}"; chmod 700 "${SEAL_DIR}"
    local home; home="$(seal_tmp_home)" || return 1
    generate_key "Loupe recovery key" "${home}" || { seal_drop_home "${home}"; echo "key generation failed" >&2; return 1; }
    "${GPG}" --homedir "${home}" --batch --no-tty --armor --export > "${SEAL_PUBLIC}.new"
    mv -f -- "${SEAL_PUBLIC}.new" "${SEAL_PUBLIC}"
    cat <<TEXT

Save everything from the BEGIN line to the END line in your password manager, as one note.
This is the only time it is shown. It is not written to disk here. Without it, encrypted backups cannot be opened.

TEXT
    "${GPG}" --homedir "${home}" --batch --no-tty --pinentry-mode loopback --passphrase '' --armor --export-secret-keys
    seal_drop_home "${home}"
    echo
    if [[ -t 0 ]]; then
        echo "Now copy it back FROM the password manager and paste it here. That proves the saved copy works."
        do_confirm_key || return 1
        printf '\nThe weekly restore test needs a key on this server to open backups. A second key does that; the\nrecovery key stays off the server. Make it? [y/N] '
        local answer; read -r answer
        if [[ "${answer}" == [yY]* ]]; then do_new_drill_key; fi
    else
        echo "Then run: backup-crypt.sh confirm-key < saved-key"
    fi
}

do_confirm_key() {
    [[ -s "${SEAL_PUBLIC}" ]] || { echo "no recovery key here: run new-key first" >&2; return 1; }
    local home line pasted="" want got secret probe rc=1
    home="$(seal_tmp_home)" || return 1
    probe="${home}/probe"
    while IFS= read -r line; do
        pasted+="${line}"$'\n'
        [[ "${line}" == *"END PGP PRIVATE KEY BLOCK"* ]] && break
    done
    secret="${home}/saved.asc"
    printf '%s' "${pasted}" > "${secret}"
    want="$(seal_fingerprint "${SEAL_PUBLIC}" "${home}")"
    openssl rand -hex 32 > "${probe}"
    "${GPG}" --homedir "${home}" --batch --quiet --no-tty --trust-model always --recipient-file "${SEAL_PUBLIC}" \
        --output "${probe}.gpg" --encrypt "${probe}" 2>/dev/null
    if open_begin "${secret}"; then
        got="$(open_file "${probe}.gpg" 2>/dev/null)" || got=""
        open_end
        [[ -n "${got}" && "${got}" == "$(cat "${probe}")" ]] && rc=0
    fi
    seal_drop_home "${home}"
    if (( rc != 0 )); then
        echo "NOT CONFIRMED: that does not open a message sealed to the key on this box. Nothing changed." >&2
        echo "Plain backups stay until a saved key proves it can open them. Try again: backup-crypt.sh confirm-key" >&2
        return 1
    fi
    printf 'fingerprint=%s\nconfirmed_utc=%s\n' "${want}" "$(date -u +%FT%TZ)" > "${SEAL_CUSTODY}"
    echo "CONFIRMED: the saved key opens this box's backups (fingerprint ${want})."
    echo "From the next nightly run, backups are encrypted only, and older plain ones are encrypted too."
}

do_new_drill_key() {
    if [[ -s "${SEAL_DRILL_PRIVATE}" ]]; then echo "a drill key is already here: ${SEAL_DRILL_PRIVATE}"; return 0; fi
    mkdir -p "${SEAL_DIR}"; chmod 700 "${SEAL_DIR}"
    local home; home="$(seal_tmp_home)" || return 1
    generate_key "Loupe restore drill key" "${home}" || { seal_drop_home "${home}"; echo "key generation failed" >&2; return 1; }
    "${GPG}" --homedir "${home}" --batch --no-tty --pinentry-mode loopback --passphrase '' --armor --export-secret-keys > "${SEAL_DRILL_PRIVATE}.new"
    "${GPG}" --homedir "${home}" --batch --no-tty --armor --export > "${SEAL_DRILL_PUBLIC}"
    mv -f -- "${SEAL_DRILL_PRIVATE}.new" "${SEAL_DRILL_PRIVATE}"
    seal_drop_home "${home}"
    echo "drill key made: sets written from now on open with it, on this box only."
}

do_status() {
    local root="${BACKUP_ROOT:-/mnt/owl-data/backups}" state store plain sealed hand
    state="$(seal_state)"
    echo "state: ${state}"
    [[ -s "${SEAL_DRILL_PRIVATE}" ]] && echo "drill key: on this box" || echo "drill key: none"
    for store in scheduled neo4j chroma; do
        plain="$(find "${root}/${store}" -type f \( -name '*.dump' -o -name 'hnsw.tar' -o -name 'chroma.sqlite3' \) -not -path '*/.*' 2>/dev/null | wc -l)"
        sealed="$(find "${root}/${store}" -type f -name '*.gpg' -not -path '*/.*' 2>/dev/null | wc -l)"
        printf '%s: %s plain, %s sealed\n' "${store}" "${plain}" "${sealed}"
    done
    hand="$(find "${root}" "${HAND_DUMPS:-/mnt/owl-data/db-backups}" -maxdepth 1 -type f -name '*.dump' 2>/dev/null | wc -l)"
    printf 'hand-made dumps left plain: %s (no timer seals these; use seal-file)\n' "${hand}"
}

do_open() {  # <file.gpg> <private key file>
    [[ -f "${1:-}" && -f "${2:-}" ]] || { echo "usage: $0 open <file.gpg> <private key file>" >&2; return 2; }
    seal_hash_ok "$1" || { echo "$1 does not match its .sha256" >&2; return 1; }
    open_begin "$2" || { echo "that key file does not import" >&2; return 1; }
    local rc=0
    open_file "$1" || rc=$?
    open_end
    return "${rc}"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    set -uo pipefail
    umask 077
    LOG_NAME=backup-crypt
    . "$(dirname "${BASH_SOURCE[0]}")/backup-lib.sh"
    case "${1:-}" in
        new-key) do_new_key ;;
        confirm-key) do_confirm_key ;;
        new-drill-key) do_new_drill_key ;;
        status) do_status ;;
        seal-file) [[ -f "${2:-}" ]] || { echo "usage: $0 seal-file <file>" >&2; exit 2; }; [[ "$(seal_state)" != none ]] || { echo "no recovery key here" >&2; exit 1; }; seal_one "$2" ;;
        open) shift; do_open "$@" ;;
        *) echo "usage: $0 new-key|confirm-key|new-drill-key|status|seal-file <file>|open <file.gpg> <key file>" >&2; exit 2 ;;
    esac
fi
