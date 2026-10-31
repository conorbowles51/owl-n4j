"""The page image cache: a page is rendered once, served again byte for byte, and only after the route's checks.

Measured 2026-10-30 (lens-evidence): every view of a PDF page rendered it again (0.07-1.15 s of CPU per page,
'private, no-store', no ETag), so a reopened document or a scroll back cost the same as the first view.  These tests
pin the cache's contract: the same bytes as a fresh render, a 304 only for the exact image, a key that changes when
anything the image depends on changes, a damaged file rendered again rather than shown, the size cap honoured, and a
render skipped when the browser has gone away.
"""
import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from services import page_image_cache as cache

try:
    import pymupdf as _pdf
except ImportError:  # pragma: no cover - the library is optional on some test boxes
    try:
        import fitz as _pdf
    except ImportError:
        _pdf = None

SHA = 'a' * 64


def _png(tag=b'x'):
    """A byte string the cache accepts as a whole PNG (signature, an IHDR-sized header, the IEND trailer)."""
    return (b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + (1200).to_bytes(4, 'big') + (1553).to_bytes(4, 'big')
            + tag + b'IEND\xaeB`\x82')


class _Request:
    def __init__(self, headers=None, gone=False):
        self.headers = headers or {}
        self.gone = gone

    async def is_disconnected(self):
        return self.gone


class CacheTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='page-cache-test-'))
        self.file = self.root / 'statement.pdf'
        self.file.write_bytes(b'%PDF-1.4 pretend')
        self.env = mock.patch.dict(os.environ, {'LOUPE_PAGE_CACHE_DIR': str(self.root / 'cache')})
        self.env.start()
        cache._reset_for_tests()

    def tearDown(self):
        self.env.stop()
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def counting_render(self, png=None, count=7):
        calls = []

        def render():
            calls.append(1)
            return (png or _png()), count
        return render, calls


class TestRunTests(unittest.TestCase):
    def test_a_test_run_never_writes_to_the_real_cache(self):
        import tests  # noqa: F401 - the package sets the directory before any test module runs
        configured = os.environ.get('LOUPE_PAGE_CACHE_DIR')
        self.assertTrue(configured)
        self.assertNotEqual(Path(configured), Path.home() / '.cache' / 'loupe-page-images')


class KeyTests(CacheTestCase):
    def test_every_input_of_the_image_is_in_the_key(self):
        base = cache.entry_for(self.file, SHA, page=1, width=1200)
        self.assertNotEqual(base, cache.entry_for(self.file, 'b' * 64, page=1, width=1200))
        self.assertNotEqual(base, cache.entry_for(self.file, SHA, page=2, width=1200))
        self.assertNotEqual(base, cache.entry_for(self.file, SHA, page=1, width=1400))
        self.assertNotEqual(base, cache.entry_for(self.file, SHA, page=1, width=1200, variant='strip1of3'))
        with mock.patch.object(cache, '_renderer_version', 'm9.9-other'):
            self.assertNotEqual(base.etag, cache.entry_for(self.file, SHA, page=1, width=1200).etag)

    def test_a_file_changed_in_place_is_a_new_key(self):
        before = cache.entry_for(self.file, SHA, page=1, width=1200)
        stat = self.file.stat()
        os.utime(self.file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        self.assertNotEqual(before.etag, cache.entry_for(self.file, SHA, page=1, width=1200).etag)
        self.file.write_bytes(b'%PDF-1.4 pretend, longer')
        self.assertNotEqual(before.path, cache.entry_for(self.file, SHA, page=1, width=1200).path)

    def test_no_sha_or_cache_switched_off_means_no_entry(self):
        self.assertIsNone(cache.entry_for(self.file, None, page=1, width=1200))
        self.assertIsNone(cache.entry_for(self.file, 'short', page=1, width=1200))
        with mock.patch.dict(os.environ, {'LOUPE_PAGE_CACHE_DIR': ''}):
            self.assertIsNone(cache.entry_for(self.file, SHA, page=1, width=1200))

    def test_the_renderer_version_names_the_library_and_the_render_code(self):
        version = cache.renderer_version()
        self.assertTrue(version.startswith('m'))
        self.assertRegex(version, r'-[0-9a-f]{12}$')


class StoreTests(CacheTestCase):
    def test_rendered_once_then_served_byte_for_byte(self):
        entry = cache.entry_for(self.file, SHA, page=3, width=1200)
        render, calls = self.counting_render(_png(b'page three'))
        first = cache.get_or_render(entry, render)
        second = cache.get_or_render(entry, render)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first[0], second[0])
        self.assertEqual((first[1], first[2], second[1], second[2]), (7, False, 7, True))

    def test_a_third_request_waits_with_the_second_rather_than_render_beside_it(self):
        import threading
        entry = cache.entry_for(self.file, SHA, page=1, width=1200)
        started, release, renders = threading.Event(), threading.Event(), []

        def slow():
            renders.append(1)
            started.set()
            release.wait(5)
            return _png(), 3
        threads = [threading.Thread(target=cache.get_or_render, args=(entry, slow)) for _ in range(3)]
        threads[0].start()
        started.wait(5)
        threads[1].start()
        threads[2].start()
        time.sleep(0.2)  # both are waiting on the first
        release.set()
        for thread in threads:
            thread.join(5)
        self.assertEqual(len(renders), 1)
        self.assertEqual(cache._key_locks, {})

    def test_a_damaged_file_is_rendered_again_not_shown(self):
        entry = cache.entry_for(self.file, SHA, page=1, width=1200)
        render, calls = self.counting_render()
        cache.get_or_render(entry, render)
        entry.path.write_bytes(_png()[:-5])  # torn: no IEND trailer
        png, _, cached = cache.get_or_render(entry, render)
        self.assertEqual((len(calls), cached, png), (2, False, _png()))

    def test_a_render_that_fails_stores_nothing(self):
        entry = cache.entry_for(self.file, SHA, page=1, width=1200)

        def broken():
            raise ValueError('no such page')
        with self.assertRaises(ValueError):
            cache.get_or_render(entry, broken)
        self.assertFalse(entry.path.exists())

    def test_a_disk_short_of_space_is_not_written_but_the_image_is_served(self):
        entry = cache.entry_for(self.file, SHA, page=1, width=1200)
        render, calls = self.counting_render()
        with mock.patch.object(cache, '_room', return_value=False):
            png, _, _ = cache.get_or_render(entry, render)
            cache.get_or_render(entry, render)
        self.assertEqual((png, len(calls)), (_png(), 2))
        self.assertFalse(entry.path.exists())
        self.assertEqual(cache.stats()['not_stored']['disk_low']['count'], 2)

    def test_over_the_cap_the_least_recently_used_go_first(self):
        entries = [cache.entry_for(self.file, SHA, page=n, width=1200) for n in range(1, 6)]
        now = time.time()
        for age, entry in zip((50, 40, 30, 20, 10), entries):
            cache.store(entry, _png(b'.' * 1000), 5)
            os.utime(entry.path, (now - age, now - age))
        size = entries[0].path.stat().st_size
        with mock.patch.dict(os.environ, {'LOUPE_PAGE_CACHE_MAX_BYTES': str(size * 4)}):
            scan = cache.sweep()
        kept = [entry.path.exists() for entry in entries]
        self.assertEqual(kept, [False, False, True, True, True])  # down to 80% of the cap: 3 of 5
        self.assertEqual((scan['files'], scan['bytes']), (3, size * 3))

    def test_a_served_image_counts_as_recently_used(self):
        entry = cache.entry_for(self.file, SHA, page=1, width=1200)
        cache.store(entry, _png(), 5)
        os.utime(entry.path, (1, 1))
        cache.read(entry)
        self.assertGreater(entry.path.stat().st_mtime, 1)

    def test_the_admin_figures_say_where_how_full_and_the_cap(self):
        cache.store(cache.entry_for(self.file, SHA, page=1, width=1200), _png(), 5)
        figures = cache.stats()
        self.assertEqual((figures['enabled'], figures['files'], figures['max_bytes']),
                         (True, 1, cache.DEFAULT_MAX_BYTES))
        self.assertEqual(figures['directory'], str(self.root / 'cache'))
        self.assertIn('disk_free_fraction', figures)


class ServeTests(CacheTestCase):
    def serve(self, request, entry, render):
        return asyncio.run(cache.serve(request, entry, render))

    def test_first_view_renders_then_the_same_bytes_without_a_render_then_304(self):
        entry = cache.entry_for(self.file, SHA, page=2, width=1200)
        render, calls = self.counting_render(_png(b'two'), count=9)
        first = self.serve(_Request(), entry, render)
        second = self.serve(_Request(), entry, render)
        third = self.serve(_Request({'if-none-match': entry.etag}), entry, render)
        self.assertEqual(len(calls), 1)
        self.assertEqual((first.status_code, second.status_code, third.status_code), (200, 200, 304))
        self.assertEqual(first.body, second.body)
        self.assertEqual(third.body, b'')
        for response in (first, second, third):
            self.assertEqual(response.headers['etag'], entry.etag)
            self.assertEqual(response.headers['cache-control'], 'private, no-cache')
            self.assertEqual(response.headers['x-pdf-page-count'], '9')
        self.assertEqual(first.headers['x-pdf-page-image-size'], '1200x1553')

    def test_another_images_etag_is_not_a_304(self):
        entry = cache.entry_for(self.file, SHA, page=2, width=1200)
        other = cache.entry_for(self.file, SHA, page=3, width=1200)
        render, _ = self.counting_render()
        self.assertEqual(self.serve(_Request({'if-none-match': other.etag}), entry, render).status_code, 200)

    def test_a_browser_that_has_gone_away_is_not_rendered_for(self):
        entry = cache.entry_for(self.file, SHA, page=2, width=1200)
        render, calls = self.counting_render()
        response = self.serve(_Request(gone=True), entry, render)
        self.assertEqual((response.status_code, calls), (cache.CLIENT_GONE, []))
        self.assertFalse(entry.path.exists())

    def test_without_a_key_the_answer_is_as_before(self):
        render, calls = self.counting_render()
        response = self.serve(_Request(), None, render)
        self.assertEqual((response.status_code, response.body, len(calls)), (200, _png(), 1))
        self.assertEqual(response.headers['cache-control'], 'private, no-store')
        self.assertNotIn('etag', response.headers)


@unittest.skipIf(_pdf is None, 'PyMuPDF is not installed')
class RealRenderTests(CacheTestCase):
    def test_a_stored_page_is_byte_identical_to_a_fresh_render(self):
        from services.financial.page_render import render_page_png
        document = _pdf.open()
        for text in ('one', 'two'):
            page = document.new_page(width=612, height=792)
            page.insert_text((72, 72), f'Statement page {text}')
        document.save(self.file)
        document.close()
        sha = 'c' * 64
        for number in (1, 2):
            entry = cache.entry_for(self.file, sha, page=number, width=900)
            with _pdf.open(self.file) as opened:
                fresh = render_page_png(opened, page_number=number, width=900)
                stored, count, _ = cache.get_or_render(
                    entry, lambda: (render_page_png(opened, page_number=number, width=900), opened.page_count))
            again, _, cached = cache.get_or_render(entry, lambda: self.fail('rendered again'))
            self.assertEqual((stored, again, count, cached), (fresh, fresh, 2, True))

    def test_the_vision_reader_renders_each_strip_once(self):
        from services.financial import vision_reader as vr
        document = _pdf.open()
        document.new_page(width=612, height=792).insert_text((72, 72), 'Page one')
        document.save(self.file)
        document.close()
        first = vr.render_pages(self.file, [1], width=800, strips=3, sha256=SHA)
        with mock.patch.object(vr, '_strip_png', side_effect=AssertionError('rendered again')):
            second = vr.render_pages(self.file, [1], width=800, strips=3, sha256=SHA)
        uncached = vr.render_pages(self.file, [1], width=800, strips=3)
        self.assertEqual(first, second)
        self.assertEqual(first, uncached)
        self.assertEqual(len(first[0][1]), 3)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
