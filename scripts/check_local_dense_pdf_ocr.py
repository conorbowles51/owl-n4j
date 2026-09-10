"""Read-only local OCR acceptance; never changes stored case evidence or readings."""
import asyncio
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'evidence-engine'))
from app.pipeline.pdf_extraction import extract_pdf

PDF = ROOT / 'data/loupe-test-pdfs/006406-006461 Hopper Lashika 0225 esubp resp_Redacted.pdf'
SHA = '5a3ad9b75a08280af2d80240974831fed7848105fc3a6168b47bb365947e9409'

async def main():
    assert hashlib.sha256(PDF.read_bytes()).hexdigest() == SHA
    async def progress(value):
        print(json.dumps({'completed': value.completed, 'total': value.total, 'pdf_page': value.pdf_page}), flush=True)
    output = ROOT / 'data/local-runtime/dense-ocr-pdf-extraction.json'
    if sys.argv[1:] == ['--verify-saved']:
        from types import SimpleNamespace
        result = SimpleNamespace(**json.loads(output.read_text()))
    elif not sys.argv[1:]:
        result = await extract_pdf(str(PDF), progress_callback=progress)
        output.write_text(json.dumps({'text': result.text, 'metadata': result.metadata}, indent=2))
    else:
        raise SystemExit('Use no arguments for local OCR or --verify-saved to inspect its saved output.')
    spans = result.metadata['page_spans']
    recovered = [p for p in spans if p['page'] in (51, 52)]
    assert len(recovered) == 2
    assert all(p['extraction_method'] == 'tesseract_ocr' and p['detection_reason'] == 'suspicious_text_layer' and p['text_origin'] == 'recognised_glyphs' for p in recovered)
    assert 'Payment History' in result.text
    assert hashlib.sha256(PDF.read_bytes()).hexdigest() == SHA
    report = dict(source_sha256=SHA, pages=len(spans), ocr_pages=result.metadata['ocr_page_count'],
                  recovered_pages=recovered, local_provider='tesseract', financial_writes=0,
                  original_unchanged=True, stored_case_sources_unchanged=True,
                  limitation='OCR text recovery only. Financial amounts and dates are not automatically verified; OCR pages do not yet have stored table geometry from this diagnostic.')
    (ROOT / 'data/local-runtime/dense-ocr-check.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({**report, 'recovered_pages':[51,52]}), flush=True)

if __name__ == '__main__':
    asyncio.run(main())
