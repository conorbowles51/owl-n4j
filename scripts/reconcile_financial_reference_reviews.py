"""Compare two supplied reader reviews; unresolved disagreements return exit 2."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ['PYTHON_DOTENV_DISABLED'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.financial.reference_reviews import reconcile_reference_reviews, parse_review_json


def read(path):
    with path.open('rb') as source:
        content = source.read(16 * 1024 * 1024 + 1)
    if len(content) > 16 * 1024 * 1024:
        raise ValueError('Reader/adjudication input exceeds 16 MiB.')
    return parse_review_json(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first', type=Path)
    parser.add_argument('second', type=Path)
    parser.add_argument('--adjudication', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = reconcile_reference_reviews(read(args.first), read(args.second),
        adjudication=read(args.adjudication) if args.adjudication else None)
    content = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False)
    if len(content.encode('utf-8')) > 64 * 1024 * 1024:
        raise ValueError('Review record exceeds 64 MiB; no partial record produced.')
    with args.output.open('x') as output:
        output.write(content)
    print(report['status'] + ': ' + str(report['unresolved_count']) + ' unresolved rows. No source interpretation or provider call.')
    return 2 if report['unresolved_count'] else 0


if __name__ == '__main__':
    sys.exit(main())
