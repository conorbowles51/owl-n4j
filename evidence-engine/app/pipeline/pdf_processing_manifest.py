"""Bounded PDF preparation runtime record; no environment dump or provider calls."""
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path


def capture_pdf_processing_manifest(*, settings, ocr_used):
    packages = {}
    for name in ('PyMuPDF', 'pytesseract', 'Pillow'):
        try: packages[name] = version(name)
        except PackageNotFoundError: packages[name] = None
    sources = {}
    for name in ('pdf_extraction.py', 'ocr_geometry.py', 'pdf_processing_manifest.py'):
        try: sources[name] = hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        except OSError: sources[name] = None
    tesseract = dict(status='not_used', version=None)
    if ocr_used:
        import pytesseract
        try:
            # No shell, source path or document bytes are passed to the executable.
            result = subprocess.run([pytesseract.pytesseract.tesseract_cmd, '--version'],
                capture_output=True, timeout=3, check=True)
            first_line = result.stdout.decode('utf-8', errors='replace').splitlines()[0][:256]
            tesseract = dict(status='reported' if first_line else 'unavailable', version=first_line or None)
        except (OSError, subprocess.SubprocessError, IndexError):
            tesseract = dict(status='unavailable', version=None)
    content = dict(schema_version='loupe.pdf_processing_manifest/1',
        recorded_at=datetime.now(timezone.utc).isoformat(), python_version=platform.python_version(),
        packages=packages, source_files_sha256=sources, tesseract=tesseract,
        settings={name:getattr(settings,name) for name in ('pdf_ocr_dpi','pdf_ocr_max_pixels','pdf_ocr_page_timeout_seconds','pdf_ocr_max_concurrency','tesseract_lang','max_pdf_pages')},
        limitation='Observed local runtime/package versions and on-disk source fingerprints at preparation completion. Not proof of loaded-code identity or immutable executables. Tesseract language-data and dependency binary hashes are not captured. No credentials, environment dump or source file paths are included.')
    raw=json.dumps(content,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    return dict(content=content,sha256=hashlib.sha256(raw).hexdigest())
