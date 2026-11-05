#!/usr/bin/env bash
# Sealing with real gpg and throwaway keys: the three states, and that no plain file goes before custody is proven.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root:?}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
script="${source_dir}/backup-crypt.sh"
export SEAL_DIR="${test_root}/keys"
mkdir -p "${SEAL_DIR}"
fail() { echo "FAIL: $*"; exit 1; }
crypt() { bash "${script}" "$@"; }
data="${test_root}/data"; mkdir -p "${data}"
head -c 300000 /dev/urandom > "${data}/a.dump"
want="$(sha256sum < "${data}/a.dump")"

# none: no key, a seal request refuses, nothing is written.
[[ "$(crypt status | sed -n 1p)" == "state: none" ]] || fail "state is not none"
if crypt seal-file "${data}/a.dump" 2>/dev/null; then fail "sealed with no key"; fi
[[ ! -e "${data}/a.dump.gpg" ]] || fail "wrote a sealed file with no key"

# new-key shows the private key once, keeps only the public half, and does not claim custody.
crypt new-key < /dev/null > "${test_root}/shown"
sed -n '/BEGIN PGP PRIVATE/,/END PGP PRIVATE/p' "${test_root}/shown" > "${test_root}/private.asc"
grep -q 'END PGP PRIVATE KEY BLOCK' "${test_root}/private.asc" || fail "private key not shown"
grep -rq 'PRIVATE KEY' "${SEAL_DIR}" && fail "a private key was left on disk"
[[ -s "${SEAL_DIR}/recovery-public.asc" ]] || fail "no public key"
[[ "$(crypt status | sed -n 1p)" == "state: unconfirmed" ]] || fail "custody claimed with no proof"
if crypt new-key < /dev/null 2>/dev/null; then fail "new-key replaced a key that sets depend on"; fi

# unconfirmed: sealed AND plain. The trap in the brief: a lost key must lose nothing.
crypt seal-file "${data}/a.dump"
[[ -s "${data}/a.dump" ]] || fail "plain file removed before custody"
[[ -s "${data}/a.dump.gpg" && -s "${data}/a.dump.gpg.sha256" ]] || fail "not sealed"
( cd "${data}" && sha256sum -c --quiet a.dump.gpg.sha256 ) || fail "sidecar is not the ciphertext's hash"

# A wrong key does not confirm custody.
GNUPGHOME="${test_root}/other"; mkdir -m 700 "${GNUPGHOME}"
gpg --homedir "${GNUPGHOME}" --batch --quiet --passphrase '' --quick-generate-key other future-default default never 2>/dev/null
gpg --homedir "${GNUPGHOME}" --batch --armor --pinentry-mode loopback --passphrase '' --export-secret-keys > "${test_root}/wrong.asc"
gpgconf --homedir "${GNUPGHOME}" --kill all
if crypt confirm-key < "${test_root}/wrong.asc" 2>/dev/null; then fail "a wrong key confirmed custody"; fi
if crypt confirm-key < /dev/null 2>/dev/null; then fail "nothing pasted confirmed custody"; fi
[[ ! -e "${SEAL_DIR}/recovery-custody" ]] || fail "custody file after a failed proof"

# The right key opens the set, and the bytes are the same.
[[ "$(crypt open "${data}/a.dump.gpg" "${test_root}/private.asc" | sha256sum)" == "${want}" ]] || fail "did not open to the same bytes"
# A wrong key opens nothing; a changed byte is refused before the key is tried.
if crypt open "${data}/a.dump.gpg" "${test_root}/wrong.asc" > /dev/null 2>&1; then fail "a wrong key opened it"; fi
cp "${data}/a.dump.gpg" "${data}/keep"
printf 'x' | dd of="${data}/a.dump.gpg" bs=1 seek=2000 conv=notrunc 2>/dev/null
if crypt open "${data}/a.dump.gpg" "${test_root}/private.asc" > /dev/null 2>&1; then fail "a changed byte opened"; fi
mv "${data}/keep" "${data}/a.dump.gpg"

# confirmed: only with the saved key; then plain goes, and a later key change drops back to keeping plain.
crypt confirm-key < "${test_root}/private.asc" > /dev/null
[[ "$(crypt status | sed -n 1p)" == "state: confirmed" ]] || fail "custody not recorded"
head -c 200000 /dev/urandom > "${data}/b.dump"
crypt seal-file "${data}/b.dump"
[[ ! -e "${data}/b.dump" && -s "${data}/b.dump.gpg" ]] || fail "plain file stayed after custody"
mv "${SEAL_DIR}/recovery-public.asc" "${SEAL_DIR}/old-public"
crypt new-key < /dev/null > /dev/null
[[ "$(crypt status | sed -n 1p)" == "state: unconfirmed" ]] || fail "custody of the old key counted for a new one"
rm -f "${SEAL_DIR}/recovery-public.asc" "${SEAL_DIR}/recovery-custody"; mv "${SEAL_DIR}/old-public" "${SEAL_DIR}/recovery-public.asc"

# A sealing failure keeps the plain file and alerts.
crypt confirm-key < "${test_root}/private.asc" > /dev/null
cat > "${test_root}/badgpg" <<'X'
#!/usr/bin/env bash
case "$*" in *--encrypt*) exit 2 ;; esac
exec gpg "$@"
X
chmod +x "${test_root}/badgpg"
head -c 1000 /dev/urandom > "${data}/c.dump"
out="$(bash -c '. "$1"; log() { :; }; alert() { echo "ALERT $1"; }; GPG="$2" seal_one "$3"' _ "${script}" "${test_root}/badgpg" "${data}/c.dump")"
grep -q 'ALERT c.dump could not be encrypted' <<<"${out}" || fail "no alert: ${out}"
[[ -s "${data}/c.dump" && ! -e "${data}/c.dump.gpg" ]] || fail "a failed seal lost the plain file or left a sealed one"

# A cut-off sealed twin never takes the plain file with it: the next run seals again. The first line of the file is intact.
head -c 200000 /dev/urandom > "${data}/e.dump"
bash -c '. "$1"; log() { :; }; alert() { :; }; seal_file "$2"' _ "${script}" "${data}/e.dump"
cp "${data}/e.dump" "${data}/e.keep"
truncate -s 20000 "${data}/e.dump.gpg"
bash -c '. "$1"; log() { :; }; alert() { :; }; seal_pending "$2" 1 "e.dump"' _ "${script}" "${data}"
[[ ! -e "${data}/e.dump" ]] || fail "plain stays after a good reseal"
[[ "$(crypt open "${data}/e.dump.gpg" "${test_root}/private.asc" | sha256sum)" == "$(sha256sum < "${data}/e.keep")" ]] || fail "the plain file went with a cut-off twin"

# The drill key is a second recipient: what it seals opens with either key.
crypt new-drill-key > /dev/null
head -c 1000 /dev/urandom > "${data}/d.dump"
crypt seal-file "${data}/d.dump"
mkdir -p "${data}/root"; : > "${data}/root/hand.dump"
BACKUP_ROOT="${data}/root" HAND_DUMPS=/none crypt status | grep -q 'hand-made dumps left plain: 1' || fail "hand-made dump not in status"
[[ "$(crypt open "${data}/d.dump.gpg" "${SEAL_DIR}/drill-private.asc" | wc -c)" == 1000 ]] || fail "drill key does not open a set"
[[ "$(crypt open "${data}/d.dump.gpg" "${test_root}/private.asc" | wc -c)" == 1000 ]] || fail "recovery key does not open a set with two recipients"
leftover="$(find /dev/shm -maxdepth 1 -name 'loupe-seal.*' -user "$(id -un)" -newer "${test_root}/shown" | wc -l)"
[[ "${leftover}" -eq 0 ]] || fail "${leftover} key homes left in memory"
echo "test-backup-crypt: all passed"
