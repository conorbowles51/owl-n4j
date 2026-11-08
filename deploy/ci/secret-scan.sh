#!/usr/bin/env bash
# Secret scan: gitleaks over the repository's full history (which includes the tree
# of every commit, so the current tree is covered). Read-only against the git dir.
# Usage: secret-scan.sh <repo-path> <outdir>
# Secret values are never written out: --redact=100 masks every match in the report.
set -euo pipefail
. "$(dirname "$0")/ci-lib.sh"

repo=$1; out=$2
mkdir -p "$out"

set +e
$CI_NICE "$(gitleaks_bin)" git "$repo" \
  --redact=100 --no-banner --exit-code 9 \
  --report-format json --report-path "$out/gitleaks.json" \
  > "$out/gitleaks.log" 2>&1
rc=$?
set -e
# exit 9 = findings (a result); 0 = clean; anything else is a scan failure.
if [ $rc -ne 0 ] && [ $rc -ne 9 ]; then
  echo "gitleaks failed (exit $rc)" >> "$out/gitleaks.log"
  echo '{"error": "gitleaks failed, see gitleaks.log"}' > "$out/secret-counts.json"
  exit 1
fi

python3 - "$out" <<'EOF'
import json, sys, os
out = sys.argv[1]
findings = json.load(open(os.path.join(out, "gitleaks.json")))
# One line per finding: rule, file, commit — never the secret itself.
seen = {}
for f in findings:
    key = (f.get("RuleID"), f.get("File"))
    seen.setdefault(key, []).append(f.get("Commit", "")[:12])
with open(os.path.join(out, "secret-findings.txt"), "w") as fh:
    for (rule, path), commits in sorted(seen.items()):
        fh.write(f"{rule}\t{path}\tcommits: {', '.join(sorted(set(commits))[:5])}{' …' if len(set(commits)) > 5 else ''}\n")
json.dump({"secret_findings": len(findings), "distinct_rule_file_pairs": len(seen)},
          open(os.path.join(out, "secret-counts.json"), "w"), indent=1)
print(json.dumps({"secret_findings": len(findings), "distinct_rule_file_pairs": len(seen)}))
EOF
