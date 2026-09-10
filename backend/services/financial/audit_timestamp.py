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
