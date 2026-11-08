#!/usr/bin/env bash
# The per-customer Terraform stays isolated: a plan for a fictional customer creates
# everything inside its own new project and shares nothing with the live project.
# Fails on the old code (no deploy/provision) and on any resource that targets an
# existing project. Needs terraform (deploy/ci/bootstrap-tools.sh) and an initialised
# deploy/provision; skips with a message otherwise rather than passing silently.
set -euo pipefail
test_root="$(mktemp -d)"
trap 'rm -rf -- "${test_root:?}"' EXIT
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
prov="${source_dir}/provision"
. "${source_dir}/ci/ci-lib.sh"

fail() { echo "FAIL: $*"; exit 1; }
tf="$(terraform_bin)"
[ -x "${tf}" ] || { echo "SKIP: terraform not installed (run deploy/ci/bootstrap-tools.sh first)"; exit 0; }
[ -d "${prov}/.terraform" ] || { echo "SKIP: deploy/provision not initialised (terraform init)"; exit 0; }

"${tf}" -chdir="${prov}" validate -no-color > "${test_root}/validate.log" 2>&1 \
    || fail "terraform validate failed: $(cat "${test_root}/validate.log")"

"${tf}" -chdir="${prov}" plan -input=false -refresh=false -no-color \
    -var customer=isolation-test \
    -var billing_account=000000-000000-000000 \
    -var alert_email=ops@example.com \
    -var inventory_dir="${test_root}/inventory" \
    -out="${test_root}/plan.tfplan" > "${test_root}/plan.log" 2>&1 \
    || fail "terraform plan failed: $(tail -5 "${test_root}/plan.log")"

"${tf}" -chdir="${prov}" show -json "${test_root}/plan.tfplan" > "${test_root}/plan.json"

python3 - "${test_root}/plan.json" <<'EOF' || exit 1
import json, subprocess, sys
plan = json.load(open(sys.argv[1]))
changes = plan.get("resource_changes", [])
problems = []
if not changes:
    problems.append("empty plan: nothing would be provisioned")
for c in changes:
    if c["change"]["actions"] != ["create"]:
        problems.append(f"{c['address']}: action {c['change']['actions']} (only create is allowed)")
    after = c["change"].get("after") or {}
    project = after.get("project", "")
    if project and project != "loupe-isolation-test":
        problems.append(f"{c['address']}: targets project {project}, not the customer's own")
# No existing project may appear anywhere in the plan.
existing = []
try:
    existing = subprocess.run(
        ["gcloud", "projects", "list", "--format=value(projectId)"],
        capture_output=True, text=True, timeout=60).stdout.split()
except Exception:
    pass  # no gcloud (CI runner): the per-resource project check above still holds
blob = json.dumps(plan)
for p in existing:
    if p in blob:
        problems.append(f"plan references the existing project {p}")
for pr in problems:
    print(f"FAIL: {pr}")
sys.exit(1 if problems else 0)
EOF

echo "ok: plan for a fictional customer is create-only, inside its own project, no shared resource with any existing project"
