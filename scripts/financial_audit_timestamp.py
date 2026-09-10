"""Prepare an offline timestamp request or verify a retained RFC 3161 response."""
import argparse
import json
import os
from pathlib import Path
import sys
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.financial.audit_timestamp import prepare_request, verify_response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--openssl', default='openssl', help='OpenSSL 3 executable')
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('archive', type=Path)
    prepare.add_argument('--output', type=Path, required=True, help='New request directory')
    verify = commands.add_parser('verify')
    verify.add_argument('archive', type=Path)
    verify.add_argument('--request', type=Path, required=True)
    verify.add_argument('--response', type=Path, required=True)
    verify.add_argument('--ca-file', type=Path, required=True)
    verify.add_argument('--untrusted', type=Path)
    verify.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output must be new.')
    if args.command == 'prepare':
        digest = prepare_request(args.archive, args.output, openssl=args.openssl)
        print(f'Prepared offline request; checkpoint SHA-256 {digest}. No network call made.')
    else:
        result = verify_response(args.archive, args.request, args.response, args.ca_file,
                                 openssl=args.openssl, untrusted=args.untrusted)
        with args.output.open('x') as target:
            json.dump(result, target, indent=2, sort_keys=True)
        print('Verified signature, nonce and checkpoint against the supplied trust roots.')


if __name__ == '__main__':
    main()
