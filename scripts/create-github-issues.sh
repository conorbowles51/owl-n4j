#!/usr/bin/env bash
#
# Create GitHub Issues for the Alex-call roadmap from tickets/tickets.json.
#
# Source of truth:  tickets/tickets.json   (edit there, re-run here)
# Plan rationale:   .claude/plans/alex-call-roadmap.md
#
# Prerequisites:
#   1. gh CLI installed:        https://cli.github.com
#   2. Authenticated:           gh auth login
#   3. jq installed:            brew install jq
#
# Behaviour:
#   - Idempotent labels & milestones (created only if missing).
#   - Issues are matched by their "S#-##" id prefix in the title; an existing
#     open/closed issue with the same id prefix is skipped (not duplicated).
#   - Pass --dry-run to print what WOULD happen without writing anything.
#
# Usage:
#   scripts/create-github-issues.sh            # create everything
#   scripts/create-github-issues.sh --dry-run  # preview only

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TICKETS="$HERE/tickets/tickets.json"
PLAN_DOC=".claude/plans/alex-call-roadmap.md"

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

command -v gh >/dev/null || { echo "ERROR: gh CLI not found. Install: https://cli.github.com"; exit 1; }
command -v jq >/dev/null || { echo "ERROR: jq not found. Install: brew install jq"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "ERROR: not authenticated. Run: gh auth login"; exit 1; }
[[ -f "$TICKETS" ]] || { echo "ERROR: $TICKETS not found"; exit 1; }

REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
echo "Repository: $REPO"
[[ $DRY_RUN -eq 1 ]] && echo "(dry-run \u2014 no writes)"
echo

run() { if [[ $DRY_RUN -eq 1 ]]; then echo "  WOULD: $*"; else "$@"; fi; }

# ---- Labels -----------------------------------------------------------------
echo "== Labels =="
existing_labels="$(gh label list --limit 200 --json name --jq '.[].name' 2>/dev/null || true)"
jq -c '.labels[]' "$TICKETS" | while read -r row; do
  name="$(jq -r '.name' <<<"$row")"
  color="$(jq -r '.color' <<<"$row")"
  desc="$(jq -r '.description' <<<"$row")"
  if grep -qxF "$name" <<<"$existing_labels"; then
    echo "  exists: $name"
  else
    echo "  create: $name"
    run gh label create "$name" --color "$color" --description "$desc"
  fi
done
echo

# ---- Milestones (via REST; gh has no native milestone create) ---------------
echo "== Milestones =="
existing_ms="$(gh api "repos/$REPO/milestones?state=all" --jq '.[].title' 2>/dev/null || true)"
jq -c '.milestones[]' "$TICKETS" | while read -r row; do
  title="$(jq -r '.title' <<<"$row")"
  desc="$(jq -r '.description' <<<"$row")"
  if grep -qxF "$title" <<<"$existing_ms"; then
    echo "  exists: $title"
  else
    echo "  create: $title"
    run gh api "repos/$REPO/milestones" -f title="$title" -f description="$desc" >/dev/null
  fi
done
echo

# ---- Issues -----------------------------------------------------------------
echo "== Issues =="
# Titles of issues that already exist (open or closed), to dedupe by id prefix.
existing_titles="$(gh issue list --state all --limit 500 --json title --jq '.[].title' 2>/dev/null || true)"

jq -c '.tickets[]' "$TICKETS" | while read -r row; do
  id="$(jq -r '.id' <<<"$row")"
  raw_title="$(jq -r '.title' <<<"$row")"
  milestone="$(jq -r '.milestone' <<<"$row")"
  body="$(jq -r '.body' <<<"$row")"
  labels="$(jq -r '.labels | join(",")' <<<"$row")"
  full_title="$id — $raw_title"

  if grep -qF "$id — " <<<"$existing_titles" || grep -qF "$id " <<<"$existing_titles"; then
    echo "  skip (exists): $full_title"
    continue
  fi

  full_body="$body

---
Plan: \`$PLAN_DOC\` (task **$id**)
Tracked from the Alex call roadmap. See the plan doc for epic context and verification gates."

  echo "  create: $full_title  [$labels]  {$milestone}"
  run gh issue create \
    --title "$full_title" \
    --body "$full_body" \
    --label "$labels" \
    --milestone "$milestone"
done

echo
if [[ $DRY_RUN -eq 1 ]]; then echo "Done. (dry-run)"; else echo "Done."; fi
echo "Tip: create a Project board and add these issues, columns grouped by the epic: labels."
