#!/usr/bin/env bash
# Portable integration test of the allocator switch: real install/mv/rm in a
# temporary directory, inert systemctl/sudo only. No host unit is touched.
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
calls() { wc -l < "${test_root}/systemctl-calls" | tr -d ' '; }
: > "${test_root}/systemctl-calls"
source "${test_root}/deploy/ingestion-safety.sh"
export BACKEND_ALLOCATOR_SWITCH="${test_root}/allocator-switch"
unit="${test_root}/units/owl-backend-v2.service.d/backend-allocator.conf"

# Off by default: no switch file installs nothing and reloads nothing.
configure_backend_allocator <&-
test ! -e "${unit}"
test "$(calls)" = 0

# Any value other than mimalloc is off.
printf 'jemalloc\n' > "${BACKEND_ALLOCATOR_SWITCH}"
configure_backend_allocator <&-
test ! -e "${unit}"
test "$(calls)" = 0

# On: one complete drop-in, mode 644, one reload; repeating changes nothing.
printf ' mimalloc \n' > "${BACKEND_ALLOCATOR_SWITCH}"
configure_backend_allocator <&-
printf '[Service]\nEnvironment=PYTHONMALLOC=mimalloc\n' > "${test_root}/expected"
cmp "${unit}" "${test_root}/expected"
mode="$(stat -c '%a' "${unit}" 2>/dev/null || stat -f '%Lp' "${unit}")"
test "${mode}" = 644
test "$(calls)" = 1
configure_backend_allocator <&-
test "$(calls)" = 1
test -z "$(ls -A "${test_root}/scratch")"
test ! -e "${test_root}/units/owl-backend-v2.service.d/.backend-allocator.conf.tmp"

# Switching off removes the drop-in and reloads once.
rm -f -- "${BACKEND_ALLOCATOR_SWITCH}"
configure_backend_allocator <&-
test ! -e "${unit}"
test "$(calls)" = 2
configure_backend_allocator <&-
test "$(calls)" = 2

# An unavailable unit directory fails without a reload or a leftover source.
printf 'mimalloc\n' > "${BACKEND_ALLOCATOR_SWITCH}"
rm -rf -- "${test_root}/units"
printf 'directory unavailable\n' > "${test_root}/units"
if configure_backend_allocator <&-; then
    echo 'Installer unexpectedly accepted an unavailable unit directory' >&2
    exit 1
fi
test "$(calls)" = 2
test -z "$(ls -A "${test_root}/scratch")"
echo 'backend allocator checks passed'
