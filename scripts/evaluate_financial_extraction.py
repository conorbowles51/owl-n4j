"""Offline extraction measurement. Supply reviewed labels; never calls a model."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from services.financial.extraction_evaluation import evaluate_extraction, compare_extraction_evaluations
from services.financial.reference_reviews import parse_review_json

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,help='Earlier corpus run with the same reviewed ground truth; exit 2 on regression.')
    parser.add_argument('--review-record',type=Path,help='Verified two-reader reconciliation record. With this option, corpus and baseline contain extraction_predictions/1 inputs.')
    parser.add_argument('--prepared-corpus',type=Path,help='Optional new file retaining the exact evaluation input assembled from --review-record and predictions.')
    args=parser.parse_args()
    if args.prepared_corpus and not args.review_record:parser.error('--prepared-corpus requires --review-record.')
    outputs=[args.output]+([args.prepared_corpus] if args.prepared_corpus else [])
    if len({path.resolve() for path in outputs})!=len(outputs) or any(path.exists() for path in outputs):parser.error('Output paths must be distinct new files.')
    if args.corpus.stat().st_size>16*1024*1024:
        parser.error('Corpus exceeds 16 MiB.')
    corpus=parse_review_json(args.corpus.read_text())
    record=None
    if args.review_record:
        if args.review_record.stat().st_size>64*1024*1024:parser.error('Review record exceeds 64 MiB.')
        from services.financial.reference_reviews import evaluation_from_reference_reviews
        record=parse_review_json(args.review_record.read_text())
        corpus=evaluation_from_reference_reviews(record,corpus)
    result=evaluate_extraction(corpus)
    if record:result['reference_review_sha256']=record['review_record_sha256']
    if args.baseline:
        if args.baseline.stat().st_size>16*1024*1024:parser.error('Baseline exceeds 16 MiB.')
        baseline=parse_review_json(args.baseline.read_text())
        if record:baseline=evaluation_from_reference_reviews(record,baseline)
        result['comparison']=compare_extraction_evaluations(baseline,corpus)
    if args.prepared_corpus:
        with args.prepared_corpus.open('x') as target:json.dump(corpus,target,indent=2,sort_keys=True)
    with args.output.open('x') as target:json.dump(result,target,indent=2,sort_keys=True)
    if result.get('comparison',{}).get('status')=='regression':
        print('Extraction regression detected; see output report.',file=sys.stderr)
        return 2
    print(f'Wrote {len(result["layers"])} layer measurements; label status: {result["label_status"]}. No provider called.')

if __name__=='__main__':sys.exit(main())
