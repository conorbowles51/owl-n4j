"""Rendered PDF pages kept on disk, so a page is rendered once and not on every view.

A page image is a pure function of the file's bytes, the page, the width, what is rendered (the whole page or one
strip of it) and the renderer.  The key is exactly those: the file's stored sha256 together with the size and
modification time the file has on disk now (a file changed in place is a different key, so it can only miss, never
serve the old image), the page, the width, the variant, and the renderer version (the PyMuPDF version plus a digest
of the code that renders).  Nothing about who asked is in the key, and nothing is served from here without the
route's own access check having run first: the HTTP answer carries an ETag with ``private, no-cache``, so a browser
asks again on every view and gets a 304 only after the check.

Measured 2026-10-31 (cold 700 KB reads, O_DIRECT, under idle IO priority): the root SSD 1.0-1.5 ms median, 2.4-2.8 ms
p90; /mnt/owl-data 2.7-3.5 ms median, 9.8-35 ms p90.  So the cache lives on the root disk, in the service user's
cache directory, size-capped (LOUPE_PAGE_CACHE_MAX_BYTES, 4 GB by default) and never written while that disk has
less than 10% free.  An image that is not stored is still served; it is only rendered again next time.

Writes are atomic (a temporary file renamed into place), and a stored file is checked for the PNG signature and
the IEND trailer before it is served, so a torn or damaged file is rendered again rather than shown.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 4 * 1024 ** 3
MIN_FREE_FRACTION = 0.10
EVICT_TO_FRACTION = 0.8
SWEEP_EVERY_S = 30.0
STALE_TEMP_S = 600.0

_PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
_PNG_TRAILER = b'IEND\xaeB`\x82'


def cache_dir():
    """LOUPE_PAGE_CACHE_DIR, else the user's cache directory; set to empty, the cache is off."""
    configured = os.environ.get('LOUPE_PAGE_CACHE_DIR')
    if configured is not None:
        return Path(configured) if configured else None
    return Path.home() / '.cache' / 'loupe-page-images'


def max_bytes():
    try:
        return int(os.environ.get('LOUPE_PAGE_CACHE_MAX_BYTES', DEFAULT_MAX_BYTES))
    except ValueError:
        return DEFAULT_MAX_BYTES


_renderer_version = None


def renderer_version():
    """PyMuPDF's version and a digest of page_render.py: either changing is a new key."""
    global _renderer_version
    if _renderer_version is None:
        try:
            from importlib import metadata
            library = metadata.version('pymupdf')
        except Exception:  # noqa: BLE001 - no library: nothing renders, the key only has to differ
            library = 'none'
        source = (Path(__file__).resolve().parent / 'financial' / 'page_render.py').read_bytes()
        _renderer_version = f"m{library}-{hashlib.sha256(source).hexdigest()[:12]}"
    return _renderer_version


@dataclass(frozen=True)
class Entry:
    """Where one rendered image is (or would be) kept, and the ETag that names it."""
    path: Path
    pages_path: Path
    etag: str


def entry_for(file_path, sha256, *, page, width, variant='page'):
    """The cache entry for this image, or None when the cache is off or the file cannot be identified."""
    root = cache_dir()
    if root is None or not isinstance(sha256, str) or len(sha256) != 64:
        return None
    try:
        stat = os.stat(file_path)
    except OSError:
        return None
    identity = f"{sha256.lower()}-{stat.st_size}-{stat.st_mtime_ns}"
    name = f"{variant}-p{int(page)}-w{int(width)}-{renderer_version()}.png"
    folder = root / identity[:2] / identity
    etag = '"' + hashlib.sha256(f"{identity}/{name}".encode()).hexdigest()[:32] + '"'
    return Entry(path=folder / name, pages_path=folder / 'pages', etag=etag)


def _valid(png):
    return len(png) > 20 and png.startswith(_PNG_SIGNATURE) and png.endswith(_PNG_TRAILER)


def read(entry):
    """The stored image, or None (absent, damaged, or the cache off)."""
    if entry is None:
        return None
    try:
        png = entry.path.read_bytes()
    except OSError:
        return None
    if not _valid(png):
        logger.warning('Page cache: %s is not a whole PNG; rendering it again', entry.path)
        return None
    try:
        os.utime(entry.path)  # recency for eviction
    except OSError:
        pass
    return png


def page_count(entry):
    if entry is None:
        return None
    try:
        value = int(entry.pages_path.read_text())
    except (OSError, ValueError):
        return None
    return value if value >= 1 else None


def image_size(png):
    """'WIDTHxHEIGHT' in pixels from the PNG header, or None."""
    if len(png) < 24 or not png.startswith(_PNG_SIGNATURE):
        return None
    return f"{int.from_bytes(png[16:20], 'big')}x{int.from_bytes(png[20:24], 'big')}"


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(temporary, 'wb') as handle:
            handle.write(data)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _room(root):
    try:
        usage = os.statvfs(root if root.exists() else root.parent)
    except OSError:
        return False
    return usage.f_bavail / max(usage.f_blocks, 1) >= MIN_FREE_FRACTION


def store(entry, png, count):
    """Keep this image (and its file's page count). False when it was not kept; the caller serves it anyway."""
    if entry is None or not _valid(png):
        return False
    root = cache_dir()
    if not _room(root):
        _note_refusal('disk_low')
        return False
    try:
        if count is not None and page_count(entry) != count:
            _atomic_write(entry.pages_path, str(int(count)).encode())
        _atomic_write(entry.path, png)
    except OSError:
        logger.warning('Page cache: could not write %s', entry.path, exc_info=True)
        _note_refusal('write_failed')
        return False
    _sweep_if_due()
    return True


_key_locks = {}
_key_locks_guard = threading.Lock()


def get_or_render(entry, render):
    """(png, page_count, cached): the stored image, else ``render()`` -> (png, page_count), stored for next time.

    One render per key at a time in this process: a second request for the same page waits for the first and
    reads what it stored.  ``render`` raises whatever the caller maps to its answer; nothing is stored then.
    """
    if entry is None:
        png, count = render()
        return png, count, False
    with _key_locks_guard:
        # [lock, holders]: the lock leaves the map only when no thread holds or waits for it, so a third request
        # never makes a second lock and renders beside a waiting second one.
        held = _key_locks.setdefault(entry.path, [threading.Lock(), 0])
        held[1] += 1
    try:
        with held[0]:
            count = page_count(entry)
            png = read(entry) if count is not None else None
            if png is not None:
                _count('hits')
                return png, count, True
            png, count = render()
            _count('misses')
            store(entry, png, count)
            return png, count, False
    finally:
        with _key_locks_guard:
            held[1] -= 1
            if not held[1]:
                _key_locks.pop(entry.path, None)


# --- size cap, eviction and what the admin page shows -------------------------------------------------------------

_stats_lock = threading.Lock()
_counters = dict(hits=0, misses=0, not_modified=0, evicted_files=0, evicted_bytes=0)
_last_sweep = 0.0
_last_scan = None
_refusals = {}


def _count(name, amount=1):
    with _stats_lock:
        _counters[name] += amount


def _note_refusal(reason):
    with _stats_lock:
        _refusals[reason] = dict(count=_refusals.get(reason, {}).get('count', 0) + 1, at=time.time())


def _scan(root):
    files, temporaries, total = [], [], 0
    for folder, _, names in os.walk(root):
        for name in names:
            path = os.path.join(folder, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            if name.endswith('.tmp'):
                temporaries.append((stat.st_mtime, path))
            elif name.endswith('.png'):
                files.append((stat.st_mtime, stat.st_size, path))
                total += stat.st_size
    return files, temporaries, total


def sweep(now=None):
    """Remove leftover temporary files and, over the cap, the least recently used images down to 80% of it."""
    global _last_sweep, _last_scan
    root = cache_dir()
    if root is None or not root.exists():
        return None
    now = time.time() if now is None else now
    files, temporaries, total = _scan(root)
    for mtime, path in temporaries:
        if now - mtime > STALE_TEMP_S:
            try:
                os.unlink(path)
            except OSError:
                pass
    cap = max_bytes()
    removed_files = removed_bytes = 0
    if total > cap:
        target = cap * EVICT_TO_FRACTION
        for mtime, size, path in sorted(files):
            if total <= target:
                break
            try:
                os.unlink(path)
            except OSError:
                continue
            total -= size
            removed_files += 1
            removed_bytes += size
        if removed_files:
            logger.info('Page cache: evicted %d images (%d bytes) to stay under %d bytes', removed_files,
                        removed_bytes, cap)
    with _stats_lock:
        _counters['evicted_files'] += removed_files
        _counters['evicted_bytes'] += removed_bytes
        _last_sweep = now
        _last_scan = dict(at=now, files=len(files) - removed_files, bytes=total)
    return _last_scan


def _sweep_if_due():
    with _stats_lock:
        due = time.time() - _last_sweep >= SWEEP_EVERY_S
    if due:
        try:
            sweep()
        except Exception:  # noqa: BLE001 - the image was stored; a failed sweep is retried at the next write
            logger.warning('Page cache sweep failed', exc_info=True)


def stats():
    """What the admin page shows: where the cache is, how full, the cap, and this process's hits and misses."""
    root = cache_dir()
    if root is None:
        return dict(enabled=False, directory=None)
    scan = sweep() if root.exists() else dict(at=time.time(), files=0, bytes=0)
    try:
        usage = os.statvfs(root if root.exists() else root.parent)
        free_fraction = usage.f_bavail / max(usage.f_blocks, 1)
    except OSError:
        free_fraction = None
    with _stats_lock:
        counters = dict(_counters)
        refusals = {key: dict(value) for key, value in _refusals.items()}
    return dict(enabled=True, directory=str(root), files=scan['files'], bytes=scan['bytes'], max_bytes=max_bytes(),
                disk_free_fraction=free_fraction, min_free_fraction=MIN_FREE_FRACTION,
                writing=free_fraction is not None and free_fraction >= MIN_FREE_FRACTION,
                renderer_version=renderer_version(), process=dict(pid=os.getpid(), **counters),
                not_stored=refusals)


def _reset_for_tests():
    global _last_sweep, _last_scan, _renderer_version
    with _stats_lock:
        for key in _counters:
            _counters[key] = 0
        _refusals.clear()
        _last_sweep, _last_scan = 0.0, None
    _renderer_version = None


# --- serving one page image over HTTP -----------------------------------------------------------------------------

# Renders get their own two slots per worker, apart from the thread pool every other request uses: measured
# 2026-10-30, 18 renders on one worker took 2.61 s wall in 18 threads against 4.33 s serially (the GIL caps the
# gain at about 1.7x), so more than two at once only takes threads from other requests.  A request waiting for a
# slot whose browser has gone away is not rendered.
RENDER_SLOTS = 2
_render_slots = None
_render_threads = None


def _limiters():
    global _render_slots, _render_threads
    if _render_slots is None:
        import anyio
        _render_slots = anyio.CapacityLimiter(RENDER_SLOTS)
        _render_threads = anyio.CapacityLimiter(RENDER_SLOTS)
    return _render_slots, _render_threads


CLIENT_GONE = 499


def _headers(entry, count, png):
    headers = {'Cache-Control': 'private, no-cache' if entry is not None else 'private, no-store'}
    if count is not None:
        headers['X-PDF-Page-Count'] = str(count)
    if entry is not None:
        headers['ETag'] = entry.etag
    size = image_size(png) if png else None
    if size:
        headers['X-PDF-Page-Image-Size'] = size
    return headers


def _matches(request, entry):
    if entry is None:
        return False
    wanted = request.headers.get('if-none-match')
    if not wanted:
        return False
    return any(tag.strip().removeprefix('W/') == entry.etag for tag in wanted.split(','))


async def serve(request, entry, render):
    """The HTTP answer for one page image: 304 when the browser already holds it, the stored copy, or a render.

    The route has already run its access check and found the file.  ``render()`` -> (png, page_count) runs in a
    worker thread and raises what the route turns into its own error answer.
    """
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import Response
    import anyio

    if _matches(request, entry):
        count = await run_in_threadpool(page_count, entry)
        _count('not_modified')
        return Response(status_code=304, headers=_headers(entry, count, None))
    if entry is not None:
        count = await run_in_threadpool(page_count, entry)
        png = await run_in_threadpool(read, entry) if count is not None else None
        if png is not None:
            _count('hits')
            return Response(content=png, media_type='image/png', headers=_headers(entry, count, png))
    if await request.is_disconnected():
        return Response(status_code=CLIENT_GONE)
    slots, threads = _limiters()
    async with slots:
        if await request.is_disconnected():
            return Response(status_code=CLIENT_GONE)
        png, count, _ = await anyio.to_thread.run_sync(get_or_render, entry, render, limiter=threads)
    return Response(content=png, media_type='image/png', headers=_headers(entry, count, png))
