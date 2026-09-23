"""Exercise actual PDF subprocesses, including simultaneous reads and cleanup."""
import asyncio
import multiprocessing
import os
import shutil
import time

import fitz
import pytest

from app.pipeline import pdf_extraction
from app.pipeline.pdf_extraction import PdfExtractionProgress, PdfOcrError


def test_native_page_checkpoint_resume_retains_exact_text_tables_and_rectangles(tmp_path,monkeypatch):
    path=tmp_path/'synthetic.pdf'; _statement(path,'checkpoint')
    root=tmp_path/'checkpoints'
    original=pdf_extraction._extract_native_tables
    read=[]
    def counted(page,number):
        read.append(number)
        return original(page,number)
    monkeypatch.setattr(pdf_extraction,'_extract_native_tables',counted)
    def interrupt(update):
        if update.pdf_page==1:raise RuntimeError('Synthetic interrupted connection')
    with pytest.raises(RuntimeError,match='interrupted connection'):
        pdf_extraction._extract_pdf_sync(str(path),interrupt,checkpoint_directory=str(root))
    assert read==[1]
    resumed=pdf_extraction._extract_pdf_sync(str(path),checkpoint_directory=str(root))
    assert read==[1,2]
    baseline=pdf_extraction._extract_pdf_sync(str(path))
    assert resumed.text==baseline.text and resumed.tables==baseline.tables
    assert resumed.metadata['table_geometry']==baseline.metadata['table_geometry']


def test_1928_page_native_document_resumes_without_dropping_or_rereading_pages(tmp_path,monkeypatch):
    path=tmp_path/'large-synthetic-chat.pdf';root=tmp_path/'pages'
    with fitz.open() as document:
        for number in range(1,1929):
            page=document.new_page()
            page.insert_textbox(fitz.Rect(25,25,560,400),
                f'Synthetic evidence page {number:04d}\n' +
                ('This is synthetic conversation text for the interruption test. '
                 'Every page must retain its original position and complete source text.\n')*5,
                fontsize=10)
        document.save(path)
    read=[];original=pdf_extraction._extract_native_tables
    def counted(page,number):
        read.append(number)
        return original(page,number)
    monkeypatch.setattr(pdf_extraction,'_extract_native_tables',counted)
    monkeypatch.setattr(pdf_extraction.settings,'max_pdf_pages',2000)
    def interrupted(update):
        if update.pdf_page==777:raise RuntimeError('Synthetic host interruption')
    with pytest.raises(RuntimeError,match='Synthetic host interruption'):
        pdf_extraction._extract_pdf_sync(str(path),interrupted,checkpoint_directory=str(root))
    assert read==list(range(1,778))
    result=pdf_extraction._extract_pdf_sync(str(path),checkpoint_directory=str(root))
    assert read==list(range(1,1929))
    assert result.metadata['page_count']==result.metadata['native_page_count']==1928
    assert result.metadata['ocr_page_count']==0
    spans=result.metadata['page_spans']
    assert len(spans)==1928
    for number,span in enumerate(spans,1):
        assert span['page']==number
        assert f'Synthetic evidence page {number:04d}' in result.text[span['start_char']:span['end_char']]


def _statement(path, code):
    with fitz.open() as document:
        for number in range(2):
            page = document.new_page(width=740, height=1040)
            page.insert_text((25, 30), f'BANK STATEMENT - EXAMPLE {code}')
            page.insert_text((25, 55), 'Account Name: Example Company')
            for x in (25, 110, 470, 550, 630, 715):
                page.draw_line((x, 100), (x, 200))
            for y in (100, 125, 150, 175, 200):
                page.draw_line((25, y), (715, y))
            data = [['Date', 'Description', 'Credit', 'Debit', 'Balance'],
                    ['2024-01-01', 'Opening Balance', '', '', '10000.00'],
                    ['2024-01-01', f'Payment from Example {code} page {number}', '12.34', '', '10012.34'],
                    ['2024-01-02', f'Payment to Example {code}', '', '2.07', '10010.27']]
            for row, cells in enumerate(data):
                for x, text in zip((30, 115, 475, 555, 635), cells):
                    page.insert_text((x, 118 + row * 25), text, fontsize=9)
        document.save(path)


async def test_simultaneous_documents_match_separate_readings_and_keep_every_cell(tmp_path):
    files = [tmp_path / f'{code}.pdf' for code in 'AB']
    for path, code in zip(files, 'AB'):
        _statement(path, code)
    baseline = [await pdf_extraction.extract_pdf(str(path)) for path in files]
    progress = []

    async def update(value):
        progress.append(value)

    concurrent = await asyncio.gather(*(pdf_extraction.extract_pdf(str(path), update) for path in files))
    for expected, actual in zip(baseline, concurrent):
        assert actual.text == expected.text
        assert actual.tables == expected.tables
        assert actual.metadata['table_geometry'] == expected.metadata['table_geometry']
        assert actual.metadata['page_count'] == 2
        assert sum('Opening Balance' in table for table in actual.tables) == 2
        assert sum('12.34' in table and '2.07' in table and '2024-01-01' in table for table in actual.tables) == 2
    assert progress and all(isinstance(p, PdfExtractionProgress) for p in progress)


def _slow_worker(connection, *_args):
    if os.name == 'posix':
        os.setsid()
    connection.send(('progress', PdfExtractionProgress('Reading', 0, 1)))
    time.sleep(60)


def _crashed_worker(connection, *_args):
    os._exit(7)


@pytest.mark.parametrize('failure', ['cancel', 'callback'])
async def test_interrupted_reading_exits_child_and_releases_its_slot(monkeypatch, failure):
    original_children = {p.pid for p in multiprocessing.active_children()}
    monkeypatch.setattr(pdf_extraction, '_pdf_worker', _slow_worker)
    entered = asyncio.Event()

    async def progress(_value):
        entered.set()
        if failure == 'callback':
            raise RuntimeError('Progress connection closed')
        await asyncio.Event().wait()

    task = asyncio.create_task(pdf_extraction.extract_pdf('unused.pdf', progress))
    await asyncio.wait_for(entered.wait(), 10)
    if failure == 'cancel':
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(RuntimeError, match='Progress connection closed'):
            await task
    assert {p.pid for p in multiprocessing.active_children()} == original_children
    assert not pdf_extraction._get_pdf_extraction_semaphore().locked()


async def test_worker_crash_is_reported_instead_of_waiting_forever(monkeypatch):
    monkeypatch.setattr(pdf_extraction, '_pdf_worker', _crashed_worker)
    with pytest.raises(PdfOcrError, match='before completing'):
        await asyncio.wait_for(pdf_extraction.extract_pdf('unused.pdf'), 10)


@pytest.mark.parametrize('interrupted', ['ai', 'financial'])
async def test_interrupting_one_pdf_never_kills_the_other_reader(monkeypatch, interrupted):
    """The second ingestion starts after the first child is already reading."""
    original_children = {p.pid for p in multiprocessing.active_children()}
    monkeypatch.setattr(pdf_extraction, '_pdf_worker', _slow_worker)
    entered = {kind: asyncio.Event() for kind in ('ai', 'financial')}

    async def progress(kind, _value):
        entered[kind].set()
        await asyncio.Event().wait()

    tasks = {}
    try:
        for kind in ('ai', 'financial'):
            tasks[kind] = asyncio.create_task(pdf_extraction.extract_pdf(
                'unused.pdf', lambda value, kind=kind: progress(kind, value)))
            await asyncio.wait_for(entered[kind].wait(), 10)
        assert len({p.pid for p in multiprocessing.active_children()} - original_children) == 2
        tasks[interrupted].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[interrupted]
        remaining = 'financial' if interrupted == 'ai' else 'ai'
        assert not tasks[remaining].done()
        children = [p for p in multiprocessing.active_children() if p.pid not in original_children]
        assert len(children) == 1 and children[0].is_alive()
    finally:
        for task in tasks.values():
            if not task.done(): task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
    assert {p.pid for p in multiprocessing.active_children()} == original_children


async def test_child_applies_the_configured_page_limit(tmp_path, monkeypatch):
    path = tmp_path / 'two-pages.pdf'
    _statement(path, 'LIMIT')
    monkeypatch.setattr(pdf_extraction.settings, 'max_pdf_pages', 1)
    with pytest.raises(PdfOcrError, match='configured limit is 1 pages'):
        await pdf_extraction.extract_pdf(str(path))


@pytest.mark.skipif(shutil.which('tesseract') is None, reason='Requires local Tesseract')
async def test_page_image_reading_runs_ocr_in_the_child_and_reports_progress(tmp_path):
    path = tmp_path / 'ocr.pdf'
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((40, 100), 'SYNTHETIC BANK STATEMENT', fontsize=20)
        page.insert_text((40, 160), 'PAYMENT EUR 1234.56', fontsize=20)
        document.save(path)
    progress = []
    async def update(value):
        progress.append(value)
    result = await pdf_extraction.extract_pdf(str(path), update, reading_mode='page_images')
    assert '1234.56' in result.text
    assert result.metadata['ocr_page_count'] == 1
    assert result.metadata['processing_manifest']['content']['settings']['pdf_reading_mode'] == 'page_images'
    assert progress[-1].completed == 1
