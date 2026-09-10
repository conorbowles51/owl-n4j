"""Exercise real OpenSSL signatures using a temporary synthetic TSA, never a real authority."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from services.financial.audit_timestamp import prepare_financial_audit_timestamp_request, verify_financial_audit_timestamp_response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--openssl', default='/opt/homebrew/opt/openssl@3/bin/openssl')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        def run(*parts):
            result = subprocess.run([args.openssl, *map(str, parts)], cwd=base,
                                    capture_output=True, timeout=20)
            if result.returncode:
                raise RuntimeError(result.stderr.decode())
        run('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'root.key',
            '-out', 'root.pem', '-days', '2', '-subj', '/CN=Synthetic test root',
            '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
        run('req', '-new', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'tsa.key',
            '-out', 'tsa.csr', '-subj', '/CN=Synthetic test timestamp signer')
        (base / 'extensions').write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=critical,timeStamping\n')
        run('x509', '-req', '-in', 'tsa.csr', '-CA', 'root.pem', '-CAkey', 'root.key',
            '-CAcreateserial', '-out', 'tsa.pem', '-days', '1', '-extfile', 'extensions')
        (base / 'serial').write_text('01')
        (base / 'tsa.cnf').write_text('''[tsa]
default_tsa=signer
[signer]
serial=serial
signer_cert=tsa.pem
certs=root.pem
signer_key=tsa.key
signer_digest=sha256
default_policy=1.2.3.4.1
digests=sha256
accuracy=secs:1
ordering=no
tsa_name=yes
ess_cert_id_chain=no
ess_cert_id_alg=sha256
''')
        request = base / 'request'
        prepare_financial_audit_timestamp_request(args.archive, request, openssl=args.openssl)
        run('ts', '-reply', '-config', 'tsa.cnf', '-queryfile', request / 'request.tsq', '-out', 'response.tsr')
        result = verify_financial_audit_timestamp_response(args.archive, request, base / 'response.tsr', base / 'root.pem', openssl=args.openssl)
        assert result['status'] == 'verified_against_supplied_trust'
        refused = []
        def reject(name, callback):
            try:
                callback()
            except ValueError:
                refused.append(name)
            else:
                raise AssertionError('Accepted invalid ' + name)
        call = lambda: verify_financial_audit_timestamp_response(args.archive, request, base / 'response.tsr', base / 'root.pem', openssl=args.openssl)
        reject('existing request output', lambda: prepare_financial_audit_timestamp_request(args.archive, request, openssl=args.openssl))
        original = (request / 'checkpoint.json').read_bytes()
        (request / 'checkpoint.json').write_bytes(original + b' ')
        reject('altered checkpoint', call)
        (request / 'checkpoint.json').write_bytes(original)
        query = (request / 'request.tsq').read_bytes()
        # Same data but a fresh nonce: response must not match this request.
        run('ts', '-query', '-data', request / 'checkpoint.json', '-sha256', '-cert', '-out', request / 'request.tsq')
        reject('different nonce', call)
        # A mutually consistent query/response for other data must still fail.
        (base / 'other').write_bytes(b'different checkpoint')
        run('ts', '-query', '-data', 'other', '-sha256', '-cert', '-out', request / 'request.tsq')
        run('ts', '-reply', '-config', 'tsa.cnf', '-queryfile', request / 'request.tsq', '-out', 'other.tsr')
        reject('swapped request and response', lambda: verify_financial_audit_timestamp_response(args.archive, request, base / 'other.tsr', base / 'root.pem', openssl=args.openssl))
        (request / 'request.tsq').write_bytes(query)
        run('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'wrong.key',
            '-out', 'wrong.pem', '-days', '1', '-subj', '/CN=Unrelated root')
        reject('untrusted signer', lambda: verify_financial_audit_timestamp_response(args.archive, request, base / 'response.tsr', base / 'wrong.pem', openssl=args.openssl))
        response = (base / 'response.tsr').read_bytes()
        (base / 'response.tsr').write_bytes(response[:-20])
        reject('truncated signature', call)
        print(json.dumps(dict(synthetic_authority_only=True, valid_signature_verified=True, invalid_inputs_refused=refused)))


if __name__ == '__main__':
    main()
