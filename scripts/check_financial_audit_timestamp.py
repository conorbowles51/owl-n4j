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
from services.financial.audit_timestamp import prepare_financial_audit_timestamp_request, verify_financial_audit_timestamp_response, submit_financial_audit_timestamp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--openssl', default='/opt/homebrew/opt/openssl@3/bin/openssl')
    parser.add_argument('--check-local-runner', action='store_true', help='Also exercise the periodic runner read-only against the fixed synthetic local case, using only this in-memory test TSA.')
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
        import httpx
        from unittest.mock import patch
        posted = []
        def responder(request):
            posted.append(request.content)
            (base / 'posted.tsq').write_bytes(request.content)
            run('ts', '-reply', '-config', 'tsa.cnf', '-queryfile', base / 'posted.tsq', '-out', 'posted.tsr')
            return httpx.Response(200, content=(base / 'posted.tsr').read_bytes(), headers={'Content-Type':'application/timestamp-reply'})
        client = httpx.Client(transport=httpx.MockTransport(responder))
        with patch('httpx.Client', return_value=client) as factory:
            submitted = submit_financial_audit_timestamp(args.archive, base / 'submitted',
                tsa_url='https://tsa.example.test?token=synthetic-secret', ca_file=base / 'root.pem', openssl=args.openssl)
        factory.assert_called_once_with(timeout=20, follow_redirects=False, trust_env=False)
        assert len(posted) == 1 and len(posted[0]) < 128
        assert submitted['status'] == 'verified_against_supplied_trust'
        assert 'synthetic-secret' not in (base / 'submitted' / 'submission.json').read_text()
        assert 'synthetic-secret' not in (base / 'submitted' / 'verification.json').read_text()
        assert (base / 'submitted' / 'roots.pem').read_bytes() == (base / 'root.pem').read_bytes()
        journal = json.loads((base / 'submitted' / 'submission.json').read_text())
        assert journal['status'] == 'verified_against_supplied_trust'
        def unavailable(request):
            raise httpx.ConnectError('private synthetic-secret', request=request)
        failed_client = httpx.Client(transport=httpx.MockTransport(unavailable))
        with patch('httpx.Client', return_value=failed_client):
            try:
                submit_financial_audit_timestamp(args.archive, base / 'failed-submission',
                    tsa_url='https://tsa.example.test?token=synthetic-secret', ca_file=base / 'root.pem', openssl=args.openssl)
            except ValueError as error:
                assert 'synthetic-secret' not in str(error)
            else:
                raise AssertionError('Failed network submission was accepted')
        assert not (base / 'failed-submission' / 'verification.json').exists()
        failed = json.loads((base / 'failed-submission' / 'submission.json').read_text())
        assert failed['status'] == 'submission_started' and failed['failure_type'] == 'ValueError'
        if args.check_local_runner:
            from sqlalchemy import create_engine, text
            from uuid import UUID
            from services.financial.periodic_audit_anchor import anchor_financial_case_once
            scope=UUID('3dfbafe7-fa6b-4bdd-9af5-0e97975447b9')
            engine=create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
            try:
                with engine.connect() as connection:
                    before=connection.scalar(text('SELECT count(*) FROM financial_audit_events WHERE case_id=:case'),{'case':scope})
                calls_before=len(posted)
                runner_client=httpx.Client(transport=httpx.MockTransport(responder))
                options=dict(case_id=scope,output=base/'periodic-runner',tsa_url='https://synthetic.example.test/tsa',ca_file=base/'root.pem',openssl=args.openssl)
                with patch('httpx.Client',return_value=runner_client):
                    first=anchor_financial_case_once(engine,**options)
                    second=anchor_financial_case_once(engine,**options)
                assert first['status']=='timestamp_verified' and second['status']=='unchanged_verified_head'
                assert len(posted)==calls_before+1 and len(posted[-1])<128
                with engine.connect() as connection:
                    assert connection.scalar(text('SELECT count(*) FROM financial_audit_events WHERE case_id=:case'),{'case':scope})==before
                print(json.dumps(dict(periodic_runner_real_local_capture=True,signature_and_nonce_verified=True,
                    unchanged_head_skipped=True,audit_database_unchanged=True,authority='in_memory_synthetic_only')))
            finally:engine.dispose()
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
        print(json.dumps(dict(synthetic_authority_only=True, valid_signature_verified=True, submission_transport_and_failure_verified=True, invalid_inputs_refused=refused)))


if __name__ == '__main__':
    main()
