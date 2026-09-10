"""Assemble captured scenarios and optional supplied validation offline.

Does not produce a complete expert packet or certify custody or ground truth.
"""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ['PYTHON_DOTENV_DISABLED'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.financial.trace_support_archive import build_trace_support_archive
from services.financial.ledger_snapshot import MAX_EXPORT_BYTES


def read_bounded(path):
    with path.open('rb') as source:
        content = source.read(MAX_EXPORT_BYTES + 1)
    if len(content) > MAX_EXPORT_BYTES:
        raise ValueError('Selected input exceeds 16 MiB.')
    return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path, nargs='+')
    parser.add_argument('--validation-corpus', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if len(args.scenario) > 8:
        parser.error('Select at most eight scenarios.')
    corpus = json.loads(read_bounded(args.validation_corpus)) if args.validation_corpus else None
    content = build_trace_support_archive([read_bounded(path) for path in args.scenario], validation_corpus=corpus)
    with args.output.open('xb') as target:
        target.write(content)
    print('Wrote selected tracing support. Complete custody and independent validation are not certified. No database or provider used.')


if __name__ == '__main__':
    main()
