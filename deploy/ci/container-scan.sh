#!/usr/bin/env bash
# Container scan: trivy over every image the production containers run (names
# starting owl-v2-). Vulnerabilities and embedded secrets; trivy masks secret
# values in its output. The vulnerability database is cached in CI_TOOLS_DIR.
# Usage: container-scan.sh <outdir>
# Heavy: each image check runs only while memory PSI full stays under the limit;
# images skipped for pressure are listed in containers-skipped.txt and the counts
# are marked partial — a clipped scan is never reported as a clean pass.
set -euo pipefail
. "$(dirname "$0")/ci-lib.sh"

out=$1
mkdir -p "$out"
cache="$CI_TOOLS_DIR/trivy-cache"
: > "$out/containers-skipped.txt"

# Scan the image each production container actually runs (by ID: a running container
# can be on an older image than its tag points to), naming the report after the
# container's image name for readability.
declare -A id_to_name=()
while read -r cname; do
  id=$(docker inspect --format '{{.Image}}' "$cname" 2>/dev/null) || continue
  iname=$(docker inspect --format '{{.Config.Image}}' "$cname" 2>/dev/null || echo "$cname")
  id_to_name["$id"]="${id_to_name[$id]:-$iname}"
done < <(docker ps --format '{{.Names}}' | grep '^owl-v2-' || true)

if [ ${#id_to_name[@]} -eq 0 ]; then
  echo "no owl-v2-* containers running on this host" > "$out/containers-skipped.txt"
fi

for id in "${!id_to_name[@]}"; do
  img="${id_to_name[$id]}"
  safe=$(echo "$img" | tr '/:' '__')
  echo "$img $id" >> "$out/scanned-images.txt"
  if ! psi_ok "${CI_PSI_LIMIT:-50}"; then
    echo "$img  skipped: memory PSI full $(psi_full)% over limit" >> "$out/containers-skipped.txt"
    continue
  fi
  set +e
  $CI_NICE "$(trivy_bin)" image "$id" \
    --cache-dir "$cache" --skip-version-check --quiet \
    --scanners vuln,secret --format json --output "$out/trivy-$safe.json" \
    > "$out/trivy-$safe.log" 2>&1
  rc=$?
  set -e
  [ $rc -ne 0 ] && echo "$img  trivy failed (exit $rc), see trivy-$safe.log" >> "$out/containers-skipped.txt"
done

python3 - "$out" <<'EOF'
import json, glob, os, sys
out = sys.argv[1]
per_image, totals = {}, {}
for p in sorted(glob.glob(os.path.join(out, "trivy-*.json"))):
    try:
        r = json.load(open(p))
    except Exception as e:
        per_image[os.path.basename(p)] = f"unreadable: {e}"
        continue
    sev = {}
    secrets = 0
    for res in r.get("Results") or []:
        for v in res.get("Vulnerabilities") or []:
            s = v.get("Severity", "UNKNOWN")
            sev[s] = sev.get(s, 0) + 1
            totals[s] = totals.get(s, 0) + 1
        secrets += len(res.get("Secrets") or [])
    if secrets:
        sev["SECRETS"] = secrets
        totals["SECRETS"] = totals.get("SECRETS", 0) + secrets
    # Key by the image name encoded in the filename (the scan target is an image ID).
    per_image[os.path.basename(p)[len("trivy-"):-len(".json")]] = sev
skipped = [l.strip() for l in open(os.path.join(out, "containers-skipped.txt")) if l.strip()]
result = {"per_image": per_image, "totals": totals, "skipped": skipped, "partial": bool(skipped)}
json.dump(result, open(os.path.join(out, "container-counts.json"), "w"), indent=1)
print(json.dumps({"totals": totals, "skipped": len(skipped)}))
EOF
