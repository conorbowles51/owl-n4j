"""Replay a downloaded Loupe scenario offline; exit 2 if its calculations differ."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ['PYTHON_DOTENV_DISABLED'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.financial.trace_replay import replay_trace
from services.financial.ledger_snapshot import MAX_EXPORT_BYTES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-sha256', help='Digest retained separately when the scenario was generated.')
    args = parser.parse_args()
    with args.scenario.open('rb') as source:
        content = source.read(MAX_EXPORT_BYTES + 1)
    result = replay_trace(content, expected_sha256=args.expected_sha256)
    with args.output.open('x') as target:
        json.dump(result, target, indent=2, sort_keys=True)
    print(result['status'] + ': ' + str(result['difference_count']) + ' differences. No database or provider used.')
    return 2 if result['difference_count'] else 0


if __name__ == '__main__':
    sys.exit(main())
