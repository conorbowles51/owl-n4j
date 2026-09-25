#!/usr/bin/env bash
# Portable integration test: real install/mv/rm, inert systemctl/sudo only.
# On Linux run in an isolated container; no host service directory is accessed.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "${test_root}/deploy" "${test_root}/commands" "${test_root}/scratch"
cp "${source_dir}/check_ingestion_idle.py" "${test_root}/deploy/"
sed "s|/etc/systemd/system/owl-backend-v2.service.d|${test_root}/units/owl-backend-v2.service.d|g" \
    "${source_dir}/ingestion-safety.sh" > "${test_root}/deploy/ingestion-safety.sh"
cat > "${test_root}/commands/sudo" <<'STUB'
#!/usr/bin/env bash
exec "$@"
STUB
chmod +x "${test_root}/commands/sudo"
export PATH="${test_root}/commands:${PATH}"
export TMPDIR="${test_root}/scratch"
PROJECT_DIR="${test_root}"
SYSTEMCTL=record_systemctl
record_systemctl() { printf '%s\n' "$*" >> "${test_root}/systemctl-calls"; }
source "${test_root}/deploy/ingestion-safety.sh"

# Closed stdin must not affect a regular-file installation. Repeating the
# installer should leave one complete, correctly permissioned unit file.
configure_ingestion_shutdown <&-
configure_ingestion_shutdown <&-
unit="${test_root}/units/owl-backend-v2.service.d/ingestion-shutdown.conf"
printf '[Service]\nTimeoutStopSec=14500\n' > "${test_root}/expected"
cmp "${unit}" "${test_root}/expected"
mode="$(stat -c '%a' "${unit}" 2>/dev/null || stat -f '%Lp' "${unit}")"
test "${mode}" = 644
test "$(wc -l < "${test_root}/systemctl-calls" | tr -d ' ')" = 2
test -z "$(ls -A "${test_root}/scratch")"
test ! -e "${test_root}/units/owl-backend-v2.service.d/.ingestion-shutdown.conf.tmp"

# A real directory creation failure must not reload systemd or leave the
# temporary source behind. The preceding installed file remains unmodified.
mv "${test_root}/units" "${test_root}/retained-units"
printf 'directory unavailable\n' > "${test_root}/units"
if configure_ingestion_shutdown <&-; then
    echo 'Installer unexpectedly accepted an unavailable unit directory' >&2
    exit 1
fi
test "$(wc -l < "${test_root}/systemctl-calls" | tr -d ' ')" = 2
test -z "$(ls -A "${test_root}/scratch")"
cmp "${test_root}/retained-units/owl-backend-v2.service.d/ingestion-shutdown.conf" "${test_root}/expected"
echo 'real install checks passed'
