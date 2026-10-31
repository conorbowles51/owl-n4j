import os

# Automatic save of fully reconciled statements (services/financial/queue_save.py)
# is ON in production. Tests of the manual save flow expect prepared statements
# to stay ready, so it is off here unless a test switches it on itself
# (tests/test_financial_queue_save.py does). Set in the package, not in a pytest
# conftest, so `unittest discover` (the documented suite command) and pytest
# both import it before any test module reads the switch.
os.environ.setdefault('FINANCIAL_AUTO_SAVE_READY', '0')

# Rendered page images (services/page_image_cache.py) go to a throwaway directory per test run, never the user's
# real cache: a suite run as the service's user would otherwise fill the live cache and its admin figures. Tests of
# the cache set their own directory. Set, not defaulted: a shell exporting the live directory must not reach it.
import atexit as _atexit
import shutil as _shutil
import tempfile as _tempfile


def _throwaway_dir(variable, prefix):
    """Point ``variable`` at a fresh directory removed at exit, unless it already names one a test run made (a child
    process re-importing this package keeps its parent's directory and registers no removal)."""
    current = os.environ.get(variable, '')
    real = os.path.realpath(current) if current else ''
    if (real and os.path.isdir(real) and os.path.dirname(real) == os.path.realpath(_tempfile.gettempdir())
            and os.path.basename(real).startswith(prefix)):
        return
    os.environ[variable] = _tempfile.mkdtemp(prefix=prefix)
    _atexit.register(_shutil.rmtree, os.environ[variable], ignore_errors=True)


_throwaway_dir('LOUPE_PAGE_CACHE_DIR', 'loupe-page-cache-tests-')

# Saved Financial views and refresh asks live in FINANCIAL_VIEW_MEMO_DIR, else ~/.cache/loupe-financial-view-memo
# (services/financial/view_cache._memo_dir). Tests that build, save, ask for or forget views must never touch a real
# one: run as the service's user, that is the live service's directory. Set, not defaulted, like the page cache: a
# shell exporting the live directory must not reach it. A test that sets the variable itself still wins.
_throwaway_dir('FINANCIAL_VIEW_MEMO_DIR', 'loupe-test-view-memo-')
