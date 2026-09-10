"""Offline release regression check against explicitly pinned reviewed artifacts.

Passing does not establish reviewer independence, representativeness or accuracy.
The caller must supply the reviewed artifact identifiers retained for this release.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.financial.reference_reviews import parse_review_json, evaluation_from_reference_reviews
from services.financial.extraction_evaluation import evaluate_extraction, compare_extraction_evaluations


def read_input(path):
    with path.open('rb') as source:
        content = source.read(16 * 1024 * 1024 + 1)
    if len(content) > 16 * 1024 * 1024:
        raise ValueError('Release input exceeds 16 MiB.')
    return parse_review_json(content), hashlib.sha256(content).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-record', type=Path, required=True)
    parser.add_argument('--expected-review-sha256', required=True,
                        help='Reconciled review digest retained independently for this release.')
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--expected-baseline-sha256', required=True,
                        help='Exact baseline predictions file digest retained for this release.')
    parser.add_argument('--current', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output must be a new file.')
    record, record_bytes = read_input(args.review_record)
    baseline, baseline_bytes = read_input(args.baseline)
    current, current_bytes = read_input(args.current)
    if (record.get('review_record_sha256') != args.expected_review_sha256
            or baseline_bytes != args.expected_baseline_sha256):
        parser.error('Review or baseline differs from the supplied release pins.')
    before = evaluation_from_reference_reviews(record, baseline)
    after = evaluation_from_reference_reviews(record, current)
    if after['label_status'] != 'independently_reviewed':
        parser.error('Synthetic labels cannot satisfy this release check.')
    for corpus in (before, after):
        if not all(document['truth'] for document in corpus['documents']):
            parser.error('Release evaluation requires reviewed transaction rows for every selected source.')
    report = evaluate_extraction(after)
    comparison = compare_extraction_evaluations(before, after)
    result = dict(schema_version='loupe.extraction_release_check/1',
        status='regression' if comparison['status'] == 'regression' else 'no_measured_regression',
        review_record_sha256=record['review_record_sha256'],
        input_file_sha256=dict(review_record=record_bytes, baseline=baseline_bytes, current=current_bytes),
        measurement=report, comparison=comparison,
        limitation='Checks pinned inputs and measured regressions only. Supplied reviewer independence, '
        'corpus representativeness, extraction execution provenance and acceptable absolute accuracy '
        'remain release-review responsibilities. No provider was called; no labels were generated.')
    with args.output.open('x') as target:
        json.dump(result, target, indent=2, sort_keys=True)
    print(result['status'])
    return 2 if result['status'] == 'regression' else 0


if __name__ == '__main__':
    sys.exit(main())
