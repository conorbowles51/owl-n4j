"""Offline extraction measurement. Supply reviewed labels; never calls a model."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from services.financial.extraction_evaluation import evaluate_extraction, compare_extraction_evaluations

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,help='Earlier corpus run with the same reviewed ground truth; exit 2 on regression.')
    args=parser.parse_args()
    if args.corpus.stat().st_size>16*1024*1024:
        parser.error('Corpus exceeds 16 MiB.')
    corpus=json.loads(args.corpus.read_text())
    result=evaluate_extraction(corpus)
    if args.baseline:
        if args.baseline.stat().st_size>16*1024*1024:parser.error('Baseline exceeds 16 MiB.')
        result['comparison']=compare_extraction_evaluations(json.loads(args.baseline.read_text()),corpus)
    with args.output.open('x') as target:json.dump(result,target,indent=2,sort_keys=True)
    if result.get('comparison',{}).get('status')=='regression':
        print('Extraction regression detected; see output report.',file=sys.stderr)
        return 2
    print(f'Wrote {len(result["layers"])} layer measurements; label status: {result["label_status"]}. No provider called.')

if __name__=='__main__':sys.exit(main())
