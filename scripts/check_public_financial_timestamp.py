"""Opt-in public TSA interoperability check sending only a synthetic checkpoint imprint.

Never accepts a case archive or document as input. Does not configure production trust.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from services.financial.audit_timestamp import prepare_financial_audit_timestamp_request, verify_financial_audit_timestamp_response

TSA_URL = 'http://timestamp.digicert.com'
ROOT_URL = 'https://cacerts.digicert.com/DigiCertTrustedRootG4.crt.pem'
INTERMEDIATE_URL = 'https://knowledge.digicert.com/content/dam/kb/attachments/time-stamp/DigiCertTrustedG4TimeStampingRSA4096SHA2562025CA1.pem'
ROOT_DER_SHA256 = '552f7bdcf1a7af9e6ce672017f4f12abf77240c78e761ac203d1d9d20ac89988'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submit-synthetic', action='store_true', help='Permit one synthetic RFC3161 request to the published DigiCert endpoint.')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--openssl', default='/opt/homebrew/opt/openssl@3/bin/openssl')
    args = parser.parse_args()
    if not args.submit_synthetic:
        parser.error('Explicit --submit-synthetic is required for this network acceptance check.')
    args.output.mkdir()
    # Test-only fixture: fixed fictional case, no documents or real case values.
    from tests.test_financial_audit_timestamp import AuditTimestampCheckpointTests
    from tests.test_financial_export_comparison import ExportComparisonTests
    archive = args.output / 'synthetic-ledger.zip'
    document = AuditTimestampCheckpointTests().document()
    document['synthetic_only'] = True
    archive.write_bytes(ExportComparisonTests().archive(document))
    request = args.output / 'request'
    prepare_financial_audit_timestamp_request(archive, request, openssl=args.openssl)
    import httpx
    def download(client, url, destination):
        with client.stream('GET', url) as response:
            response.raise_for_status()
            content = b''
            for chunk in response.iter_bytes():
                content += chunk
                if len(content) > 1024 * 1024:
                    raise ValueError('Certificate download exceeds limit.')
        destination.write_bytes(content)
    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
        download(client, ROOT_URL, args.output / 'root.cer')
        download(client, INTERMEDIATE_URL, args.output / 'intermediate.pem')
        root_content = (args.output / 'root.cer').read_bytes()
        root_format = 'PEM' if root_content.startswith(b'-----BEGIN') else 'DER'
        for output_format, filename in [('PEM','root.pem'), ('DER','root.der')]:
            subprocess.run([args.openssl,'x509','-inform',root_format,'-in',str(args.output/'root.cer'),
                '-outform',output_format,'-out',str(args.output/filename)], check=True, capture_output=True, timeout=10)
        if hashlib.sha256((args.output/'root.der').read_bytes()).hexdigest() != ROOT_DER_SHA256:
            raise ValueError('Downloaded root differs from DigiCert published fingerprint; no request submitted.')
        query = (request/'request.tsq').read_bytes()
        # One request only, containing a digest and nonce, never the checkpoint JSON.
        with client.stream('POST', TSA_URL, content=query,
                headers={'Content-Type':'application/timestamp-query','Accept':'application/timestamp-reply'}) as response:
            response.raise_for_status()
            if response.headers.get('content-type','').split(';')[0] != 'application/timestamp-reply':
                raise ValueError('Unexpected timestamp response type.')
            content = b''
            for chunk in response.iter_bytes():
                content += chunk
                if len(content) > 4 * 1024 * 1024:
                    raise ValueError('Timestamp response exceeds limit.')
        (args.output/'response.tsr').write_bytes(content)
    checked = verify_financial_audit_timestamp_response(archive, request, args.output/'response.tsr',
        args.output/'root.pem', openssl=args.openssl, untrusted=args.output/'intermediate.pem')
    checked.update(synthetic_only=True, service_url=TSA_URL, root_download_url=ROOT_URL,
        intermediate_download_url=INTERMEDIATE_URL, pinned_root_der_sha256=ROOT_DER_SHA256,
        authority_documentation='https://knowledge.digicert.com/general-information/rfc3161-compliant-time-stamp-authority-server',
        scope='One synthetic interoperability request. No real case archive, source document or financial record was sent. Production authority/trust configuration and periodic anchoring are not enabled.')
    (args.output/'verification.json').write_text(json.dumps(checked,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(status=checked['status'],synthetic_only=True,request_bytes=len(query),response_bytes=len(content),root_fingerprint_matched=True)))


if __name__ == '__main__':
    main()
