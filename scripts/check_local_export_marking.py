"""Read-only local export acceptance for actor, historical versions and PDF marks."""
import io,json,hashlib
from pathlib import Path
from zipfile import ZipFile
import httpx
from pypdf import PdfReader
case='e8ecc646-7b29-49d6-b64d-7086a9a14ad4'
with httpx.Client(base_url='http://127.0.0.1:58002',trust_env=False,timeout=120) as client:
    login=client.post('/api/auth/login',json=dict(username='loupe-local@example.com',password='Loupe-local-test-2026'))
    login.raise_for_status()
    client.headers['Authorization']='Bearer '+login.json()['access_token']
    response=client.get('/api/financial/ledger-export',params=dict(case_id=case,include_pdf='true',privilege_marking='privileged_confidential',generated_by='untrusted-query-actor'))
    response.raise_for_status()
    assert response.headers['x-loupe-privilege-marking']=='privileged_confidential'
    with ZipFile(io.BytesIO(response.content)) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        raw=archive.read('ledger-snapshot.json');snapshot=json.loads(raw)
        assert hashlib.sha256(raw).hexdigest()==manifest['document_sha256']
        context=snapshot['export_context']
        assert context['generated_by']['email']=='loupe-local@example.com'
        assert context['generated_by']==manifest['generated_by']
        assert context['generated_at']==manifest['generated_at']
        assert context['privilege_marking']==manifest['privilege_marking']=='privileged_confidential'
        assert snapshot['processing_provenance']['runs']
        support_raw=archive.read('expert-support.json');support=json.loads(support_raw)
        assert hashlib.sha256(support_raw).hexdigest()==manifest['expert_support']['sha256']
        assert support['preparation']==context
        assert support['versions']['financial_processing_runs']==snapshot['processing_provenance']['runs']
        pdf=archive.read('ledger-report.pdf')
        assert hashlib.sha256(pdf).hexdigest()==manifest['pdf_report']['sha256']
        reader=PdfReader(io.BytesIO(pdf))
        assert len(reader.pages)>1
        assert all('Privileged and confidential' in page.extract_text() for page in reader.pages)
        Path('/tmp/loupe-marked-report.pdf').write_bytes(pdf)
        print(json.dumps(dict(pages=len(reader.pages),every_page_marked=True,authenticated_exporter_captured=True,historical_versions_captured=True,hashes_verified=True,financial_writes=0)))
    invalid=client.get('/api/financial/ledger-export',params=dict(case_id=case,privilege_marking='invalid'))
    assert invalid.status_code==422
