import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def inline_pdf_worker(monkeypatch):
    """Keep OCR/geometry unit-test doubles in this interpreter.

    Process isolation, progress and cancellation have separate real-child tests
    in test_pdf_worker.py. Unit tests here need their patched OCR readers.
    """
    import asyncio
    from app.pipeline import pdf_extraction

    async def run(file_path, progress_callback=None, *, reading_mode='automatic'):
        progress = []
        result = await asyncio.to_thread(pdf_extraction._extract_pdf_sync, file_path,
            progress.append, reading_mode=reading_mode)
        if progress_callback:
            for update in progress:
                await progress_callback(update)
        return result

    monkeypatch.setattr(pdf_extraction, '_extract_pdf_in_process', run)


@pytest.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
