#!/usr/bin/env bash
# Dependency scan: pip-audit over the Python packages, npm audit over the JS lockfiles.
# Usage: deps-scan.sh <manifest-dir> <outdir>
#   <manifest-dir>: a tree holding backend/requirements.txt, frontend_v2/package{,-lock}.json,
#                   landing/package{,-lock}.json (extracted from the scanned commit).
# Nothing is installed: pip-audit runs with --disable-pip on pinned versions only, and
# npm audit reads the lockfile (--package-lock-only). What could not be audited is listed
# in <outdir>/deps-not-audited.txt — a partial result is reported as partial.
set -euo pipefail
. "$(dirname "$0")/ci-lib.sh"

src=$1; out=$2
mkdir -p "$out"
: > "$out/deps-not-audited.txt"

LIVE_VENV="${CI_LIVE_VENV:-/home/conorbowles51/app-v3/loupe-backend/current/.venv}"

# --- Python ---------------------------------------------------------------
# Two inputs, both fully pinned so nothing is installed to audit them:
#  1. the deployed backend venv (pip freeze of what actually runs), when on the box;
#  2. the pinned lines of backend/requirements.txt at the scanned commit.
# Ranged lines (no ==) are only covered by the venv freeze; without one they are
# recorded as not audited. The evidence-engine's Python packages are audited by the
# container scan (they ship inside the owl-v2-evidence images), not here.
pin_src="$out/python-pinned.txt"
grep -E '^[A-Za-z0-9_.-]+(\[[^]]*\])?==' "$src/backend/requirements.txt" > "$pin_src" || true
if [ -x "$LIVE_VENV/bin/pip" ]; then
  "$LIVE_VENV/bin/pip" list --format=freeze 2>/dev/null | grep -E '==' >> "$pin_src"
else
  grep -vE '^\s*(#|$)' "$src/backend/requirements.txt" | grep -v '==' \
    | sed 's/$/  (ranged pin, no deployed venv on this host to resolve it)/' \
    >> "$out/deps-not-audited.txt" || true
fi
sort -uf "$pin_src" -o "$pin_src"

set +e
$CI_NICE "$(pip_audit_bin)" --disable-pip --no-deps -r "$pin_src" \
  --format json --output "$out/pip-audit.json" >"$out/pip-audit.log" 2>&1
pip_rc=$?
set -e
# pip-audit exits 1 when vulnerabilities are found; that is a result, not an error.
if [ $pip_rc -gt 1 ] || [ ! -s "$out/pip-audit.json" ]; then
  echo "pip-audit failed (exit $pip_rc), see pip-audit.log" >> "$out/deps-not-audited.txt"
fi

# --- JavaScript -----------------------------------------------------------
out_abs=$(cd "$out" && pwd)
for app in frontend_v2 landing; do
  if [ -f "$src/$app/package-lock.json" ]; then
    set +e
    ( cd "$src/$app" && $CI_NICE npm audit --package-lock-only --json ) \
      > "$out_abs/npm-audit-$app.json" 2>"$out_abs/npm-audit-$app.log"
    rc=$?
    set -e
    # npm audit exits 1 on findings; that is a result, not an error.
    [ $rc -gt 1 ] && echo "npm audit $app failed (exit $rc), see npm-audit-$app.log" >> "$out_abs/deps-not-audited.txt"
  else
    echo "$app/package-lock.json missing at this commit" >> "$out/deps-not-audited.txt"
  fi
done

# --- Counts ---------------------------------------------------------------
python3 - "$out" <<'EOF'
import json, os, sys
out = sys.argv[1]
counts = {}
try:
    pa = json.load(open(os.path.join(out, "pip-audit.json")))
    vulns = [v for d in pa.get("dependencies", []) for v in d.get("vulns", [])]
    counts["pip_audit_vulns"] = len(vulns)
    counts["pip_audit_packages_with_vulns"] = sum(1 for d in pa.get("dependencies", []) if d.get("vulns"))
except Exception as e:
    counts["pip_audit_vulns"] = f"unreadable: {e}"
for app in ("frontend_v2", "landing"):
    p = os.path.join(out, f"npm-audit-{app}.json")
    try:
        na = json.load(open(p))
        sev = na.get("metadata", {}).get("vulnerabilities", {})
        counts[f"npm_{app}"] = {k: v for k, v in sev.items() if isinstance(v, int)}
    except Exception as e:
        counts[f"npm_{app}"] = f"unreadable: {e}"
counts["not_audited_lines"] = sum(1 for _ in open(os.path.join(out, "deps-not-audited.txt")))
json.dump(counts, open(os.path.join(out, "deps-counts.json"), "w"), indent=1)
print(json.dumps(counts))
EOF
