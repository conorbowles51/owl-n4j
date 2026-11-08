#!/usr/bin/env bash
# Run the three scans (dependency, secret, container) against one released commit
# and write one report under CI_REPORTS_DIR/<sha12>/. Called by scan-tick.sh for
# each new live head; can be run by hand: scan-head.sh <sha> [<repo-path>].
#
# High findings: a message goes to the coordinator inbox only when a HIGH/CRITICAL
# vulnerability, any dependency vulnerability, or any secret appears that the
# previous completed scan did not have (first scan: everything is new). Findings
# never block a release (Neil decides when they should).
set -euo pipefail
cd "$(dirname "$0")"
. ./ci-lib.sh

sha=${1:?usage: scan-head.sh <sha> [<repo-path>]}
repo=${2:-/home/conorbowles51/app-v3/owl-n4j}
sha=$(git -C "$repo" rev-parse "$sha")
s12=${sha:0:12}
out="$CI_REPORTS_DIR/$s12"
mkdir -p "$out"
tell=/mnt/owl-data/fin-wt/headless/tell.sh

ci_log "scan of $s12 starting (PSI full $(psi_full)%)" | tee -a "$out/scan.log"

# Manifests at the scanned commit, nothing else checked out.
srcdir="$out/src"
rm -rf "$srcdir"; mkdir -p "$srcdir"
for path in backend/requirements.txt frontend_v2/package.json frontend_v2/package-lock.json \
            landing/package.json landing/package-lock.json; do
  git -C "$repo" archive "$sha" "$path" 2>/dev/null | tar -x -C "$srcdir" \
    || echo "$path missing at $s12" >> "$out/deps-not-audited.txt"
done

rc_total=0
bash ./deps-scan.sh "$srcdir" "$out"       >> "$out/scan.log" 2>&1 || { rc_total=1; echo "deps-scan FAILED" >> "$out/scan.log"; }
bash ./secret-scan.sh "$repo" "$out"       >> "$out/scan.log" 2>&1 || { rc_total=1; echo "secret-scan FAILED" >> "$out/scan.log"; }
bash ./container-scan.sh "$out"            >> "$out/scan.log" 2>&1 || { rc_total=1; echo "container-scan FAILED" >> "$out/scan.log"; }

# ---- Fingerprints of every finding (stable ids, no secret values) ----------
python3 - "$out" <<'EOF'
import json, os, sys
out = sys.argv[1]
fp = set()
def load(name):
    try: return json.load(open(os.path.join(out, name)))
    except Exception: return None
pa = load("pip-audit.json")
if pa:
    for d in pa.get("dependencies", []):
        for v in d.get("vulns", []):
            fp.add(f"pip:{d.get('name')}:{d.get('version')}:{v.get('id')}")
for app in ("frontend_v2", "landing"):
    na = load(f"npm-audit-{app}.json")
    if na:
        for name, adv in (na.get("vulnerabilities") or {}).items():
            sev = adv.get("severity", "unknown")
            fp.add(f"npm:{app}:{name}:{sev}")
gl = load("gitleaks.json")
if gl:
    for f in gl:
        fp.add(f"secret:{f.get('RuleID')}:{f.get('File')}:{f.get('Commit','')[:12]}")
import glob
for p in glob.glob(os.path.join(out, "trivy-*.json")):
    try:
        tv = json.load(open(p))
    except Exception:
        continue
    # Image name from the filename: the scan target is an image ID, which changes on
    # every rebuild and would make old findings look new.
    img = os.path.basename(p)[len("trivy-"):-len(".json")]
    for res in tv.get("Results") or []:
        for v in res.get("Vulnerabilities") or []:
            fp.add(f"img:{img}:{v.get('PkgName')}:{v.get('VulnerabilityID')}:{v.get('Severity')}")
        for s in res.get("Secrets") or []:
            fp.add(f"imgsecret:{img}:{s.get('RuleID')}:{s.get('Target','')}")
with open(os.path.join(out, "fingerprints.txt"), "w") as fh:
    fh.write("\n".join(sorted(fp)) + ("\n" if fp else ""))
print(f"{len(fp)} finding fingerprints")
EOF

# ---- High findings new since the previous completed scan -------------------
prev=$(cat "$CI_REPORTS_DIR/.last-completed" 2>/dev/null || true)
new_high="$out/new-high.txt"
if [ -n "$prev" ] && [ -f "$CI_REPORTS_DIR/$prev/fingerprints.txt" ]; then
  comm -13 "$CI_REPORTS_DIR/$prev/fingerprints.txt" "$out/fingerprints.txt" > "$out/new-findings.txt" || true
else
  cp "$out/fingerprints.txt" "$out/new-findings.txt"
fi
grep -E '^(secret:|imgsecret:|pip:|npm:[^:]+:[^:]+:(high|critical)|img:.*:(HIGH|CRITICAL)$)' \
  "$out/new-findings.txt" > "$new_high" || true

# ---- Report -----------------------------------------------------------------
{
  echo "# Scan report for live head $s12 — $(date -u '+%F %H:%M') UTC"
  echo
  echo "## Counts"
  for f in deps-counts.json secret-counts.json container-counts.json; do
    echo "### $f"; echo '```json'; cat "$out/$f" 2>/dev/null || echo "missing — that scan failed, see scan.log"; echo '```'
  done
  if [ -s "$out/deps-not-audited.txt" ]; then
    echo "## Not audited (partial result)"; sed 's/^/- /' "$out/deps-not-audited.txt"
  fi
  if [ -s "$out/containers-skipped.txt" ]; then
    echo "## Container scans skipped or failed (partial result)"; sed 's/^/- /' "$out/containers-skipped.txt"
  fi
  echo
  echo "## New findings since previous scan (${prev:-none}): $(wc -l < "$out/new-findings.txt") (high: $(wc -l < "$new_high"))"
  sed 's/^/- /' "$new_high"
} > "$out/report.md"

echo "$s12" > "$CI_REPORTS_DIR/.last-completed"
echo "$(date -u +%FT%TZ) $s12 findings=$(wc -l < "$out/fingerprints.txt") new=$(wc -l < "$out/new-findings.txt") new_high=$(wc -l < "$new_high") rc=$rc_total" >> "$CI_REPORTS_DIR/scans.log"

# High findings reach the coordinator inbox (never block a release).
# CI_TELL=0 suppresses the message (used once, for the first baseline scan, whose
# findings were triaged by hand instead of dumped on the coordinator).
if [ "${CI_TELL:-1}" = 1 ] && [ -s "$new_high" ] && [ -x "$tell" ]; then
  bash "$tell" coordinator ci-scan "scan of live head $s12: $(wc -l < "$new_high") new high findings (secrets/HIGH/CRITICAL). Report: $out/report.md; list: $new_high" >> "$out/scan.log" 2>&1 || true
fi

# Keep the live-box inventory entry current (deploy/provision/inventory-update.sh).
[ -x ./inventory-update.sh ] && bash ./inventory-update.sh "$sha" >> "$out/scan.log" 2>&1 || true

rm -rf "$srcdir"
ci_log "scan of $s12 done (rc=$rc_total)" | tee -a "$out/scan.log"
exit $rc_total
