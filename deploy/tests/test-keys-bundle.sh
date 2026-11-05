#!/usr/bin/env bash
# The keys bundle, with real gpg and made-up secrets.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root:?}"' EXIT
export GNUPGHOME="${test_root}/gnupg"; mkdir -m 700 "${GNUPGHOME}"
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
script="${source_dir}/keys-bundle.sh"
dir="${test_root}/backups"; pass="${test_root}/conf/passphrase"; alerts="${test_root}/alerts"
mkdir -p "${test_root}/etc/units"
secret="not-a-real-key-$(date +%s%N)"
echo "OPENAI_API_KEY=${secret}" > "${test_root}/etc/.env"; echo unit > "${test_root}/etc/units/a.service"
paths="${test_root}/etc/.env
${test_root}/etc/units/*"
alert_cmd="${test_root}/alert"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$1" >> %q\n' "${alerts}" > "${alert_cmd}"; chmod +x "${alert_cmd}"
run() { env BACKUP_DIR="${dir}" KEYS_PASSPHRASE_FILE="${pass}" KEYS_PATHS="${paths}" BACKUP_ALERT_CMD="${alert_cmd}" LIVE_CHECKOUT="${test_root}" \
        NOW_EPOCH="$1" bash "${script}" "${@:2}" >> "${test_root}/log" 2>&1; }
fail() { echo "FAIL: $*"; echo "--- log"; cat "${test_root}/log"; exit 1; }
epoch() { date -u -d "$1" +%s; }
: > "${alerts}"

# No passphrase: no bundle and an alert.
if run "$(epoch '2026-11-05 02:05')" dump; then fail "bundle written with no passphrase"; fi
grep -q "passphrase file" "${alerts}" || fail "no alert for a missing passphrase"

run 0 init || fail "init failed"
[[ "$(stat -c %a "${pass}")" == 600 ]] || fail "passphrase file is not mode 600"
first="$(cat "${pass}")"; run 0 init; [[ "$(cat "${pass}")" == "${first}" ]] || fail "init replaced the passphrase"
grep -qF "${first}" "${test_root}/log" && fail "passphrase reached the log"

run "$(epoch '2026-11-05 02:05')" dump || fail "good bundle failed"
s="keys-20261105-0205Z"
grep -q 'files=2' "${dir}/${s}/meta.env" || fail "file count wrong"
if grep -rqF "${secret}" "${dir}"; then fail "secret in clear in the backup directory"; fi
grep -qF "${secret}" "${test_root}/log" && fail "secret reached the log"
run "$(epoch '2026-11-05 12:00')" check || fail "fresh bundle failed the check"

mkdir "${test_root}/open"
run 0 open "${s}" "${test_root}/open" || fail "open failed"
cmp "${test_root}/open/${test_root#/}/etc/.env" "${test_root}/etc/.env" || fail "opened file differs"

# A listed file gone: the bundle holds the rest, the run and the check both alert.
keep="${paths}"; paths="${paths}
${test_root}/etc/absent"
: > "${alerts}"
if run "$(epoch '2026-11-05 03:05')" dump; then fail "short bundle reported as whole"; fi
grep -q "is short" "${alerts}" || fail "no alert for a short bundle"
grep -q 'missing' "${dir}/keys-20261105-0305Z/files.tsv" || fail "absent path not listed"
: > "${alerts}"
if run "$(epoch '2026-11-05 12:00')" check; then fail "short bundle passed the check"; fi
grep -q "is short" "${alerts}" || fail "check did not say the bundle is short"
rm -rf -- "${dir:?}/keys-20261105-0305Z"; paths="${keep}"

# A wrong passphrase does not open it, and the check says so.
good="$(cat "${pass}")"; echo wrong > "${pass}"; : > "${alerts}"
if run "$(epoch '2026-11-05 12:00')" check; then fail "wrong passphrase passed the check"; fi
grep -q "does not decrypt" "${alerts}" || fail "no alert when the bundle does not decrypt"
echo "${good}" > "${pass}"
: > "${alerts}"
if run "$(epoch '2026-11-06 03:06')" check; then fail "stale bundle passed"; fi
grep -q '25 h old' "${alerts}" || fail "no stale alert"
echo "test-keys-bundle: all passed"
