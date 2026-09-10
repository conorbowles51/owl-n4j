"""Explain differences between retained ledger export ZIPs without a database."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ['PYTHON_DOTENV_DISABLED'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.financial.export_comparison import compare_ledger_exports, MAX_ARCHIVE_BYTES


def read(path):
    with path.open('rb') as source:
        content = source.read(MAX_ARCHIVE_BYTES + 1)
    return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = compare_ledger_exports(read(args.before), read(args.after))
    with args.output.open('x') as output:
        json.dump(report, output, sort_keys=True, indent=2)
    print(report['status'] + '. Original archives unchanged; no database or provider used.')


if __name__ == '__main__':
    main()
