"""Operator-started periodic timestamping; explicit cases, authority and trust required."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from uuid import UUID
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--once',action='store_true');mode.add_argument('--watch',action='store_true')
    parser.add_argument('--case-id',type=UUID,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--tsa-url',required=True)
    parser.add_argument('--ca-file',type=Path,required=True)
    parser.add_argument('--untrusted',type=Path)
    parser.add_argument('--openssl',default='openssl')
    parser.add_argument('--interval-seconds',type=int,default=3600)
    parser.add_argument('--database-url-env',default='DATABASE_URL')
    parser.add_argument('--retry-failed',action='store_true',help='Explicit one-time retry after reviewing retained uncertain attempts; only with --once.')
    args=parser.parse_args()
    if not 300<=args.interval_seconds<=86400: parser.error('Interval must be between 300 and 86400 seconds.')
    if args.retry_failed and not args.once: parser.error('Review and retry uncertain attempts once; automatic retry loops are not permitted.')
    if len(args.case_id)>100 or len(set(args.case_id))!=len(args.case_id): parser.error('Choose up to 100 distinct case IDs.')
    url=os.environ.get(args.database_url_env)
    if not url: parser.error('The selected database URL environment variable must be set explicitly.')
    if not args.ca_file.is_file() or (args.untrusted and not args.untrusted.is_file()): parser.error('Selected trust files must exist.')
    from sqlalchemy import create_engine
    from services.financial.periodic_audit_anchor import anchor_financial_case_once
    engine=create_engine(url)
    try:
        while True:
            failed=False
            for case_id in args.case_id:
                try:
                    result=anchor_financial_case_once(engine,case_id=case_id,output=args.output,tsa_url=args.tsa_url,
                        ca_file=args.ca_file,untrusted=args.untrusted,openssl=args.openssl,retry_failed=args.retry_failed)
                    failed |= result['status']=='attention_required'
                except Exception as exc:
                    failed=True;result=dict(case_id=str(case_id),status='failed',error_type=type(exc).__name__,
                        action='Inspect retained attempt files and database/audit/trust state before retrying.')
                print(json.dumps(result),flush=True)
            if args.once:return 2 if failed else 0
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:return 0
    finally:engine.dispose()


if __name__=='__main__':sys.exit(main())
