import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch
import subprocess
from app.pipeline.pdf_processing_manifest import capture_pdf_processing_manifest


def settings():
    return SimpleNamespace(pdf_ocr_dpi=300,pdf_ocr_max_pixels=1000000,pdf_ocr_page_timeout_seconds=60,
        pdf_ocr_max_concurrency=2,tesseract_lang='eng',max_pdf_pages=500,api_key='MUST_NOT_RECORD')


def test_native_manifest_is_bounded_and_does_not_probe_ocr_or_capture_secrets():
    with patch('app.pipeline.pdf_processing_manifest.subprocess.run') as run:
        result=capture_pdf_processing_manifest(settings=settings(),ocr_used=False)
        run.assert_not_called()
    content=result['content']
    assert content['tesseract']=={'status':'not_used','version':None}
    assert all(len(value)==64 for value in content['source_files_sha256'].values())
    raw=json.dumps(content,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    assert hashlib.sha256(raw).hexdigest()==result['sha256']
    assert 'MUST_NOT_RECORD' not in raw.decode() and len(raw)<16384


def test_ocr_probe_is_bounded_and_failure_remains_unavailable():
    with patch('app.pipeline.pdf_processing_manifest.subprocess.run',return_value=SimpleNamespace(stdout=b'tesseract 5.synthetic\nmore details')) as run:
        result=capture_pdf_processing_manifest(settings=settings(),ocr_used=True)
        assert result['content']['tesseract']['version']=='tesseract 5.synthetic'
        assert run.call_args.args[0][-1]=='--version'
        assert run.call_args.kwargs['timeout']==3
    with patch('app.pipeline.pdf_processing_manifest.subprocess.run',side_effect=subprocess.TimeoutExpired('tesseract',3)):
        result=capture_pdf_processing_manifest(settings=settings(),ocr_used=True)
        assert result['content']['tesseract']=={'status':'unavailable','version':None}
