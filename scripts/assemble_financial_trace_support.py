"""Assemble captured scenarios and optional supplied validation offline.

Does not produce a complete expert packet or certify custody or ground truth.
"""
import argparse
import os
from pathlib import Path
import sys

os.environ['PYTHON_DOTENV_DISABLED'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.financial.trace_support_archive import build_trace_support_archive
from services.financial.ledger_snapshot import MAX_EXPORT_BYTES
from services.financial.reference_reviews import parse_review_json
from services.financial.export_comparison import MAX_ARCHIVE_BYTES


def read_bounded(path, limit=MAX_EXPORT_BYTES):
    with path.open('rb') as source:
        content = source.read(limit + 1)
    if len(content) > limit:
        raise ValueError('Selected input exceeds its byte limit.')
    return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path, nargs='+')
    parser.add_argument('--validation-corpus', type=Path)
    parser.add_argument('--ledger-export', type=Path)
    parser.add_argument('--reference-review', type=Path)
    parser.add_argument('--validation-predictions', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if len(args.scenario) > 8:
        parser.error('Select at most eight scenarios.')
    corpus = parse_review_json(read_bounded(args.validation_corpus)) if args.validation_corpus else None
    content = build_trace_support_archive([read_bounded(path) for path in args.scenario], validation_corpus=corpus,
        ledger_archive=read_bounded(args.ledger_export, MAX_ARCHIVE_BYTES) if args.ledger_export else None,
        reference_review=parse_review_json(read_bounded(args.reference_review)) if args.reference_review else None,
        validation_predictions=parse_review_json(read_bounded(args.validation_predictions)) if args.validation_predictions else None)
    with args.output.open('xb') as target:
        target.write(content)
    print('Wrote selected tracing support. Complete custody and independent validation are not certified. No database or provider used.')


if __name__ == '__main__':
    main()
