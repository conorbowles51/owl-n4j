"""Verify a captured tracing support ZIP and compare its offline rebuild."""
import argparse
import json
import os
from pathlib import Path
import sys
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.financial.trace_support_archive import verify_trace_support_archive, MAX_SUPPORT_ARCHIVE_BYTES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--expected-sha256', help='Exact archive digest retained independently at capture.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output must be new.')
    with args.archive.open('rb') as source:
        content = source.read(MAX_SUPPORT_ARCHIVE_BYTES + 1)
    result = verify_trace_support_archive(content, expected_sha256=args.expected_sha256)
    with args.output.open('x') as target:
        json.dump(result, target, indent=2, sort_keys=True)
    print(result['status'])
    return 2 if result['status'] == 'verified_bytes_different_rebuild' else 0


if __name__ == '__main__':
    sys.exit(main())
