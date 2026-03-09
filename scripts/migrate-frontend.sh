#!/usr/bin/env bash
set -euo pipefail

# Frontend v1 → v2 Migration Script
# This script performs the cutover from frontend/ to frontend_v2/
#
# Steps:
#   1. Build v2
#   2. Archive v1
#   3. Rename v2 → frontend
#   4. Update references
#
# Usage: ./scripts/migrate-frontend.sh [--dry-run]

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "🔍 DRY RUN MODE — no changes will be made"
fi

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
V1_DIR="$PROJECT_ROOT/frontend"
V2_DIR="$PROJECT_ROOT/frontend_v2"
ARCHIVE_DIR="$PROJECT_ROOT/frontend_v1_archived"

echo "═══════════════════════════════════════"
echo "  🦉 Frontend v1 → v2 Migration"
echo "═══════════════════════════════════════"
echo ""

# Pre-flight checks
echo "📋 Pre-flight checks..."

if [[ ! -d "$V2_DIR" ]]; then
    echo "❌ frontend_v2/ directory not found"
    exit 1
fi

if [[ ! -d "$V1_DIR" ]]; then
    echo "⚠️  frontend/ directory not found (may already be migrated)"
fi

if [[ -d "$ARCHIVE_DIR" ]]; then
    echo "❌ $ARCHIVE_DIR already exists — previous migration archive found"
    exit 1
fi

# Step 1: Build v2
echo ""
echo "1️⃣  Building frontend_v2..."
if [[ "$DRY_RUN" == false ]]; then
    cd "$V2_DIR"
    npm ci
    npm run typecheck
    npm run test
    npm run build
    echo "   ✅ Build successful"
else
    echo "   [dry-run] Would run: npm ci && npm run typecheck && npm run test && npm run build"
fi

# Step 2: Archive v1
echo ""
echo "2️⃣  Archiving frontend/ → frontend_v1_archived/"
if [[ "$DRY_RUN" == false ]]; then
    if [[ -d "$V1_DIR" ]]; then
        mv "$V1_DIR" "$ARCHIVE_DIR"
        echo "   ✅ v1 archived"
    else
        echo "   ⏭️  No v1 directory to archive"
    fi
else
    echo "   [dry-run] Would run: mv frontend/ frontend_v1_archived/"
fi

# Step 3: Rename v2 → frontend
echo ""
echo "3️⃣  Renaming frontend_v2/ → frontend/"
if [[ "$DRY_RUN" == false ]]; then
    mv "$V2_DIR" "$V1_DIR"
    echo "   ✅ Renamed"
else
    echo "   [dry-run] Would run: mv frontend_v2/ frontend/"
fi

# Step 4: Update deployment references
echo ""
echo "4️⃣  Post-migration reminders:"
echo "   • Update CI/CD pipelines to use frontend/ (no longer frontend_v2/)"
echo "   • Update Nginx config to serve from frontend/dist"
echo "   • Remove /v1/ fallback route after stability period"
echo "   • Update CLAUDE.md and project documentation"
echo "   • Delete frontend_v1_archived/ after stability period"
echo ""

if [[ "$DRY_RUN" == false ]]; then
    echo "✅ Migration complete!"
else
    echo "🔍 Dry run complete — no changes were made"
fi
