#!/usr/bin/env bash
# Checkpoint A: fresh-upload statement automation benchmark on the synthetic corpus.
#
#   scripts/run_statement_benchmark.sh [--out DIR] [--concurrency N]
#
# Needs one interpreter with the backend and evidence-engine dependencies
# (SQLAlchemy, pydantic, PyMuPDF, pytesseract, Pillow) plus the tesseract
# binary. Set LOUPE_BENCH_PYTHON to choose it (default: python3). Writes only
# to the run directory (default: a new directory under $TMPDIR or /tmp).
# Exit status is 1 if any period was admitted that should not have been.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${LOUPE_BENCH_PYTHON:-python3}"
if ! "$PY" -c 'import sqlalchemy, pydantic, fitz, pytesseract, PIL' 2>/dev/null; then
  echo "The interpreter '$PY' lacks the backend/engine dependencies." >&2
  echo "Set LOUPE_BENCH_PYTHON to one that has them (see the baseline report)." >&2
  exit 2
fi
command -v tesseract >/dev/null || { echo "tesseract is not installed; OCR repair cannot be measured." >&2; exit 2; }
cd "$ROOT/backend"
exec env PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 "$PY" -m benchmarks.statement_automation.harness \
  --engine-python "$PY" "$@"
