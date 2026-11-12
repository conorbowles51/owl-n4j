#!/usr/bin/env bash
# The evidence engine refresh never replaces the API or the other workers while the main worker is still finishing
# work (11 Nov 22:51: compose replaced them first, then waited on the worker's 14500 s stop and could not name its
# successor; the API stayed down for hours and the rollback failed the same way). Runs deploy.sh's own engine lines
# against a fake docker; nothing on the host is touched.
set -euo pipefail
src="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/deploy.sh"
tmp="$(mktemp -d)"; trap 'rm -rf -- "${tmp}"' EXIT
mkdir "${tmp}/bin"
cat > "${tmp}/bin/docker" <<'FAKE'
#!/usr/bin/env bash
echo "$*" >> "${FAKE_DIR}/calls"
case "$*" in
    "compose exec -T redis redis-cli --scan --pattern arq:in-progress:*")
        [ "${FAKE_REDIS_DOWN:-0}" = 1 ] && exit 1
        for i in $(seq 1 "${FAKE_INPROGRESS:-0}"); do echo "arq:in-progress:job-${i}"; done ;;
    "compose stop evidence-engine-worker") sleep "${FAKE_STOP_SLEEP:-0}" ;;
    "compose config --services") printf '%s\n' redis evidence-engine-api evidence-engine-worker evidence-pdf-worker ;;
    "compose ps -aq evidence-engine-worker") echo c0ffee ;;
esac
exit 0
FAKE
chmod +x "${tmp}/bin/docker"
{
    echo 'set -euo pipefail; success() { echo "OK $1"; }; warn() { echo "WARN $1"; }'
    sed -n '/^COMPOSE_UP_TIMEOUT_S=/,/^engine_rollback_up() {/p' "${src}"
    sed -n '/^engine_rollback_up() {/,/^}/p' "${src}" | sed 1d
} > "${tmp}/engine.sh"
run() {  # <name> <shell lines>; prints output, exit status in ${tmp}/rc
    : > "${tmp}/calls"
    set +e
    ( export PATH="${tmp}/bin:${PATH}" FAKE_DIR="${tmp}" COMPOSE_UP_TIMEOUT_S=2 ENGINE_BUSY_WAIT_S=2 ENGINE_BUSY_POLL_S=1
      STEP_ENGINE=run LOG_FILE="${tmp}/log"; source "${tmp}/engine.sh"; eval "$2" ) > "${tmp}/out" 2>&1
    echo $? > "${tmp}/rc"; set -e
}
fail() { echo "FAIL: $1"; echo "--- out"; cat "${tmp}/out"; echo "--- calls"; cat "${tmp}/calls"; exit 1; }

# 1. Engine work in a worker's hands: the release is deferred (75) and compose replaces nothing.
run busy 'FAKE_INPROGRESS=2 engine_gate'
[ "$(cat "${tmp}/rc")" = 75 ] || fail "busy engine: exit $(cat "${tmp}/rc"), wanted 75"
grep -q 'Release deferred: 2 evidence engine jobs' "${tmp}/out" || fail "busy engine: no 'Release deferred' line"
! grep -qE 'compose (up|stop)' "${tmp}/calls" || fail "busy engine: compose touched a service"
# 2. Unreadable engine state defers too (fail closed, like the ingestion gate).
run unknown 'FAKE_REDIS_DOWN=1 engine_gate'
[ "$(cat "${tmp}/rc")" = 75 ] || fail "unreadable engine state: exit $(cat "${tmp}/rc"), wanted 75"
# 3. Idle engine: the gate passes.
run idle 'engine_gate'
[ "$(cat "${tmp}/rc")" = 0 ] || fail "idle engine: exit $(cat "${tmp}/rc"), wanted 0"
# 4. The main worker is stopped on its own first, then compose refreshes the stack.
run order 'docker_stack_up'
[ "$(cat "${tmp}/rc")" = 0 ] || fail "refresh: exit $(cat "${tmp}/rc")"
[ "$(grep -nE '^compose (stop|up)' "${tmp}/calls" | head -1 | cut -d: -f2-)" = "compose stop evidence-engine-worker" ] \
    || fail "refresh: the main worker was not stopped before compose up"
# 5. A main worker that does not stop: nothing else is replaced, the refresh fails.
run stuck 'FAKE_STOP_SLEEP=5 docker_stack_up'
[ "$(cat "${tmp}/rc")" = 1 ] || fail "stuck worker: exit $(cat "${tmp}/rc"), wanted 1"
! grep -q '^compose up' "${tmp}/calls" || fail "stuck worker: compose up replaced services while the worker was stopping"
# 6. Rollback with that worker still stopping: every other engine service comes back, and a waiter starts the worker.
run rollback 'FAKE_STOP_SLEEP=5 engine_rollback_up'
for _ in $(seq 1 20); do grep -qx 'compose up -d --no-build --no-deps evidence-engine-worker' "${tmp}/calls" && break; sleep 0.5; done
grep -qx 'compose up -d --no-build --no-deps redis evidence-engine-api evidence-pdf-worker' "${tmp}/calls" \
    || fail "rollback: the API and other workers were not brought back without the main worker"
grep -qx 'wait c0ffee' "${tmp}/calls" && grep -qx 'compose up -d --no-build --no-deps evidence-engine-worker' "${tmp}/calls" \
    || fail "rollback: no waiter started the main worker after its stop"
echo "PASS engine refresh order"
