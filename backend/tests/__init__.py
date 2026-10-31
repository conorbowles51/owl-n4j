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
os.environ['LOUPE_PAGE_CACHE_DIR'] = _tempfile.mkdtemp(prefix='loupe-page-cache-tests-')
_atexit.register(_shutil.rmtree, os.environ['LOUPE_PAGE_CACHE_DIR'], ignore_errors=True)

# Saved Financial views and refresh asks live in FINANCIAL_VIEW_MEMO_DIR, else ~/.cache/loupe-financial-view-memo
# (services/financial/view_cache._memo_dir). Tests that build, save or ask for views must never write to or delete
# from a real one: run as the service's user, that is the live service's directory. Each test run gets its own
# empty directory, removed at exit; a test that sets the variable itself still wins.
if 'FINANCIAL_VIEW_MEMO_DIR' not in os.environ:
    import atexit
    import shutil
    import tempfile
    _memo = tempfile.mkdtemp(prefix='loupe-test-view-memo-')
    os.environ['FINANCIAL_VIEW_MEMO_DIR'] = _memo
    atexit.register(shutil.rmtree, _memo, True)
