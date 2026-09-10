"""Check saved ledger archive bytes and its prospective audit chain offline."""
import argparse
import json
import os
import sys
from pathlib import Path
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.financial.export_comparison import read_verified_ledger_archive, MAX_ARCHIVE_BYTES
from services.financial.audit_chain import verify_financial_audit_chain


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--expected-head',help='SHA-256 retained independently when this chain was captured.')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Output must be a new file.')
    with args.archive.open('rb') as source:content=source.read(MAX_ARCHIVE_BYTES+1)
    document=read_verified_ledger_archive(content)['document']
    chain=(document.get('case_financial_history') or {}).get('audit_chain')
    if not chain:parser.error('This export does not include a recorded financial audit chain; export with wider case history selected.')
    checked=verify_financial_audit_chain(chain['entries'],case_id=document['ledger']['case_id'],expected_head_sha256=args.expected_head)
    saved=chain['verification']
    if any(saved.get(key)!=checked[key] for key in ('case_id','event_count','head_sha256','status')):
        parser.error('Saved verification summary differs from the actual chain.')
    result=dict(verification=checked,limitation=chain['limitation'])
    with args.output.open('x') as target:json.dump(result,target,indent=2,sort_keys=True)
    print(f'Checked {checked["event_count"]} recorded events. No database or provider called.')


if __name__=='__main__':main()
