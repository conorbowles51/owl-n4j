"""Offline RFC 3161 checkpoint requests; no network transport or default trust store."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from services.financial.audit_chain import verify_financial_audit_chain
from services.financial.export_comparison import read_verified_ledger_archive, MAX_ARCHIVE_BYTES

MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def _read(path, limit=MAX_RESPONSE_BYTES):
    with Path(path).open('rb') as source:
        content = source.read(limit + 1)
    if len(content) > limit:
        raise ValueError('Timestamp input exceeds its byte limit.')
    return content


def _json(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def checkpoint(archive):
    verified = read_verified_ledger_archive(_read(archive, MAX_ARCHIVE_BYTES))
    document = verified['document']
    chain = (document.get('case_financial_history') or {}).get('audit_chain')
    if not chain:
        raise ValueError('Export must include recorded case audit history.')
    checked = verify_financial_audit_chain(chain['entries'], case_id=document['ledger']['case_id'])
    if any(chain['verification'].get(key) != checked[key]
           for key in ('case_id', 'event_count', 'head_sha256', 'status')):
        raise ValueError('Saved audit verification differs from the recorded chain.')
    return _json(dict(schema_version='loupe.financial.audit_checkpoint/1',
        case_id=checked['case_id'], event_count=checked['event_count'],
        head_sha256=checked['head_sha256'], snapshot_sha256=verified['manifest']['document_sha256'],
        archive_sha256=verified['archive_sha256']))


def _run(openssl, arguments, directory):
    # Explicit empty locations prevent fallback to machine-wide trusted roots.
    env = dict(os.environ, SSL_CERT_FILE=str(directory / 'empty.pem'),
               SSL_CERT_DIR=str(directory / 'empty-trust'), OPENSSL_CONF=os.devnull)
    result = subprocess.run([str(openssl), *map(str, arguments)], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15, check=False)
    if result.returncode:
        raise ValueError('OpenSSL timestamp operation failed: ' + result.stdout[:3000].decode(errors='replace'))
    if len(result.stdout) > 65536:
        raise ValueError('OpenSSL timestamp output exceeds limit.')
    return result.stdout.decode(errors='replace')


def _trust_directory(directory):
    (directory / 'empty-trust').mkdir()
    (directory / 'empty.pem').write_bytes(b'')


def prepare_financial_audit_timestamp_request(archive, output, *, openssl='openssl'):
    content = checkpoint(archive)
    output = Path(output)
    if output.exists():
        raise ValueError('Request directory must be new.')
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        directory = Path(temporary)
        _trust_directory(directory)
        (directory / 'checkpoint.json').write_bytes(content)
        _run(openssl, ['ts', '-query', '-data', directory / 'checkpoint.json', '-sha256',
                      '-cert', '-out', directory / 'request.tsq'], directory)
        # Atomic creation after all validation and cryptographic work succeeded.
        (directory / 'empty-trust').rmdir()
        (directory / 'empty.pem').unlink()
        directory.rename(output)
    return hashlib.sha256(content).hexdigest()


def verify_financial_audit_timestamp_response(archive, request_directory, response, ca_file, *, openssl='openssl', untrusted=None):
    expected = checkpoint(archive)
    request_directory = Path(request_directory)
    if _read(request_directory / 'checkpoint.json') != expected:
        raise ValueError('Checkpoint does not match the supplied verified export.')
    inputs = {'checkpoint.json': expected, 'request.tsq': _read(request_directory / 'request.tsq'),
              'response.tsr': _read(response), 'roots.pem': _read(ca_file)}
    if untrusted is not None:
        inputs['intermediates.pem'] = _read(untrusted)
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        _trust_directory(directory)
        for name, content in inputs.items():
            (directory / name).write_bytes(content)
        common = ['ts', '-verify', '-in', directory / 'response.tsr',
                  '-CAfile', directory / 'roots.pem', '-CApath', directory / 'empty-trust',
                  '-CAstore', directory / 'empty-trust']
        if untrusted is not None:
            common += ['-untrusted', directory / 'intermediates.pem']
        # Query verification checks the nonce. Data verification independently binds
        # the signed imprint to the reconstructed checkpoint, not a swapped query.
        _run(openssl, common + ['-queryfile', directory / 'request.tsq'], directory)
        _run(openssl, common + ['-data', directory / 'checkpoint.json'], directory)
        detail = _run(openssl, ['ts', '-reply', '-in', directory / 'response.tsr', '-text'], directory)
        version = _run(openssl, ['version'], directory).strip()
    return dict(schema_version='loupe.financial.audit_timestamp_verification/1',
        status='verified_against_supplied_trust', checkpoint=json.loads(expected),
        input_sha256={name: hashlib.sha256(content).hexdigest() for name, content in inputs.items()},
        openssl_version=version, timestamp_response=detail,
        limitation='Offline signature, nonce and checkpoint verification against supplied roots only. '
        'This does not establish authority independence, current revocation status, complete historical custody '
        'or the truth of case evidence. Retain the original archive, request, response and trust certificates.')


def submit_financial_audit_timestamp(archive, output, *, tsa_url, ca_file, openssl='openssl', untrusted=None):
    """Explicit one-shot submission of a generated imprint request, never an archive.

    Trust files and the response remain beside the exact request for later offline
    verification. No redirects, environment proxies or automatic retries are used.
    """
    from urllib.parse import urlsplit
    import httpx
    endpoint = urlsplit(tsa_url)
    if endpoint.scheme not in ('http', 'https') or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.fragment:
        raise ValueError('Choose an HTTP(S) timestamp endpoint without embedded credentials or a fragment.')
    root_bytes = _read(ca_file)
    intermediate_bytes = _read(untrusted) if untrusted is not None else None
    output = Path(output)
    prepare_financial_audit_timestamp_request(archive, output, openssl=openssl)
    (output/'roots.pem').write_bytes(root_bytes)
    if intermediate_bytes is not None:
        (output/'intermediates.pem').write_bytes(intermediate_bytes)
    journal = dict(schema_version='loupe.financial.timestamp_submission/1', status='request_prepared',
        endpoint_sha256=hashlib.sha256(tsa_url.encode()).hexdigest(),
        endpoint_origin=f'{endpoint.scheme}://{endpoint.hostname}',
        request_sha256=hashlib.sha256(_read(output/'request.tsq')).hexdigest(),
        limitation='Endpoint query parameters are not recorded in plaintext. Request delivery can be uncertain after a network error; no retry was made automatically.')
    def save_journal():
        (output/'submission.json').write_bytes(_json(journal))
    save_journal()
    try:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); _trust_directory(directory)
            _run(openssl, ['x509','-in',output/'roots.pem','-noout'], directory)
        query = _read(output/'request.tsq', 8192)
        journal['status'] = 'submission_started'
        save_journal()
        try:
            with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
                with client.stream('POST', tsa_url, content=query,
                        headers={'Content-Type':'application/timestamp-query','Accept':'application/timestamp-reply'}) as response:
                    response.raise_for_status()
                    if response.headers.get('content-type','').split(';')[0] != 'application/timestamp-reply':
                        raise ValueError('Unexpected timestamp response type.')
                    chunks = []; size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise ValueError('Timestamp response exceeds its byte limit.')
                        chunks.append(chunk)
                    (output/'response.tsr').write_bytes(b''.join(chunks))
        except httpx.HTTPError:
            raise ValueError('Timestamp request failed; delivery may be uncertain. No automatic retry was made.') from None
        journal['status'] = 'response_received_unverified'
        save_journal()
        result = verify_financial_audit_timestamp_response(archive, output, output/'response.tsr', output/'roots.pem',
            openssl=openssl, untrusted=output/'intermediates.pem' if intermediate_bytes is not None else None)
        result['submission'] = dict(endpoint_sha256=journal['endpoint_sha256'], endpoint_origin=journal['endpoint_origin'])
        (output/'verification.json').write_bytes(_json(result))
        journal['status'] = 'verified_against_supplied_trust'
        save_journal()
        return result
    except Exception as error:
        journal['failure_type'] = type(error).__name__
        save_journal()
        raise
