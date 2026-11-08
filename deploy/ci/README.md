# deploy/ci — scan gates

Three scans run against every released head, plus the plumbing that triggers them and
keeps the instance inventory current. Nothing here blocks a release: findings are
reported, and the decision to gate on them is Neil's.

## The scans

| Script | What it scans | Tool | Measured (8 Nov 2026, load ~3) |
|---|---|---|---|
| `deps-scan.sh <manifests> <out>` | backend/requirements.txt pins + the deployed venv's freeze (pip), frontend_v2 and landing lockfiles (npm) | pip-audit (no install: `--disable-pip`), `npm audit --package-lock-only` | 117 s |
| `secret-scan.sh <repo> <out>` | full git history, every committed blob; values always redacted | gitleaks | 22 s (3450 commits) |
| `container-scan.sh <out>` | the image each running `owl-v2-*` container actually uses (by image ID, not tag) | trivy (vuln + secret, secrets masked) | 243 s for 9 images, first run incl. DB download |

The evidence-engine's Python dependencies are ranged in its pyproject and are audited
inside its images by the container scan, not by pip-audit.

Partial results are always visible: anything not audited or skipped (memory pressure,
tool failure, missing manifest) lands in `deps-not-audited.txt` /
`containers-skipped.txt` and the report marks the counts partial.

## Per-head trigger

`scan-tick.sh` runs every watchdog cycle from `headless/status.sh`, directly after the
head-suite tick, off the same signal: a new `live <sha>` line in deploy-now.log. One
scan per live head (`.last-launched`), never two at once (`.scan.lock`), detached from
the tick. Switch off with `CI_SCANS=0` in `headless/fleet-gate.conf`.

`scan-head.sh <sha>` writes one report per head under
`/mnt/owl-data/fin-wt/ci-reports/<sha12>/` (`report.md`, raw tool JSON, counts,
`fingerprints.txt`). Findings that are high (any secret, any pip vuln, HIGH/CRITICAL
npm or image vulns) **and new since the previous completed scan** go to the
coordinator inbox as one message (`tell.sh coordinator ci-scan …`). They do not block
the release.

## Tools

`bootstrap-tools.sh` installs pinned, checksum-verified copies of pip-audit, gitleaks,
trivy and terraform into `/mnt/owl-data/fin-wt/ci-tools` (override: `CI_TOOLS_DIR`).
Versions are pinned in `ci-lib.sh`. When `github.com/.../releases/download/` is
unreachable (504s seen 8 Nov 2026) it falls back to the GitHub API asset endpoint.

## Instance inventory

`inventory-update.sh` (called after each per-head scan) writes this box's entry in
`/mnt/owl-data/fin-wt/ci-reports/inventory/owl-dev.json`: customer, region (GCE
metadata), version (live sha), health (`/health` on the backend), backup state
(`/mnt/owl-data/backups/status.tsv`), last deployment. Terraform-provisioned
customers get their entry written by `deploy/provision`. `inventory-check.sh`
validates every entry (required fields, freshness) and exits 1 with each problem
listed.

## Load rules

Everything heavy runs `nice -n 15 ionice -c3`, and the container scan checks memory
PSI (`full` avg60, limit `CI_PSI_LIMIT`, default 50 %) before each image — a skipped
image is listed, never silently dropped.
