#!/usr/bin/env bash
# Real-document benchmark: the statement harness over the private tier-A truth
# corpus, read in place (sources are verified against the manifest and linked,
# never copied).
#
#   scripts/run_real_benchmark.sh --out /mnt/owl-data/fin-real/bench/<label> [--corpus DIR]
#                                 [--score verified[,ocr_reconciled]] [harness options]
#
# Only periods whose truth status is in --score are scored (default: verified).
# --out must lie inside the private real-data root (LOUPE_REAL_ROOT, default
# /mnt/owl-data/fin-real): results.json and the run database hold what was read
# from real statements. summary.md holds counts and opaque ids only.
# Engine reading runs one file at a time with single-threaded OCR.
# Exit status is 1 if any scored period was admitted that should not have been.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRIVATE="$(realpath -m "${LOUPE_REAL_ROOT:-/mnt/owl-data/fin-real}")"
OUT=""
CORPUS="$PRIVATE/truth"
CONCURRENCY=1
PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --corpus) CORPUS="$2"; shift 2 ;;
    --concurrency) CONCURRENCY="$2"; shift 2 ;;
    *) PASS+=("$1"); shift ;;
  esac
done
if [ -z "$OUT" ]; then
  echo "--out is required (a directory inside $PRIVATE)." >&2
  exit 2
fi
OUT="$(realpath -m "$OUT")"
case "$OUT/" in
  "$PRIVATE"/*) ;;
  *) echo "Refusing --out outside the private real-data root $PRIVATE." >&2; exit 2 ;;
esac
if [ ! -f "$CORPUS/manifest.json" ]; then
  echo "No manifest.json in $CORPUS (run real_truth first)." >&2
  exit 2
fi
mkdir -p "$OUT"
chmod 700 "$OUT"
export OMP_THREAD_LIMIT="${OMP_THREAD_LIMIT:-1}"
exec "$ROOT/scripts/run_statement_benchmark.sh" --corpus "$CORPUS" --out "$OUT" --concurrency "$CONCURRENCY" \
  ${PASS[@]+"${PASS[@]}"}
