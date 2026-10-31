"""The backend tests never use a real saved-views or page-image directory (tests/__init__.py)."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_the_saved_views_directory_of_a_test_run_is_its_own_temporary_one():
    import tests  # noqa: F401 - the package sets it
    from services.financial import view_cache
    memo = view_cache._memo_dir()
    assert memo is not None
    assert Path.home() / '.cache' not in memo.parents
    assert Path(tempfile.gettempdir()) in memo.parents
    assert memo.name.startswith('loupe-test-view-memo-')
    assert os.environ['FINANCIAL_VIEW_MEMO_DIR'] == str(memo)


def _directories_seen_by_a_fresh_import(environment):
    code = ("import os, tests; print(os.environ['FINANCIAL_VIEW_MEMO_DIR']); print(os.environ['LOUPE_PAGE_CACHE_DIR'])")
    out = subprocess.run([sys.executable, '-c', code], cwd=BACKEND, env=environment, capture_output=True, text=True,
                         check=True).stdout.split()
    return out[0], out[1]


def test_an_inherited_real_directory_is_replaced():
    live = str(Path.home() / '.cache' / 'loupe-financial-view-memo')
    memo, pages = _directories_seen_by_a_fresh_import({**os.environ, 'FINANCIAL_VIEW_MEMO_DIR': live,
                                                       'LOUPE_PAGE_CACHE_DIR': '/var/cache/loupe-pages'})
    assert memo != live and Path(memo).name.startswith('loupe-test-view-memo-')
    assert pages != '/var/cache/loupe-pages' and Path(pages).name.startswith('loupe-page-cache-tests-')
    assert not Path(memo).exists() and not Path(pages).exists()  # the child made them and removed them at exit


def test_a_child_of_a_test_run_keeps_the_run_s_directories():
    memo, pages = _directories_seen_by_a_fresh_import(dict(os.environ))
    assert (memo, pages) == (os.environ['FINANCIAL_VIEW_MEMO_DIR'], os.environ['LOUPE_PAGE_CACHE_DIR'])
    assert Path(memo).is_dir() and Path(pages).is_dir()  # not removed by the child's exit


def test_a_path_through_a_test_directory_or_a_link_to_a_real_one_is_replaced(tmp_path):
    run_memo = os.environ['FINANCIAL_VIEW_MEMO_DIR']
    real = tmp_path / 'real-cache'; real.mkdir()
    link = Path(tempfile.gettempdir()) / ('loupe-test-view-memo-link-%d' % os.getpid())
    link.symlink_to(real)
    try:
        for given in (run_memo + '/../../' + str(real).lstrip('/'), str(link)):
            memo, _ = _directories_seen_by_a_fresh_import({**os.environ, 'FINANCIAL_VIEW_MEMO_DIR': given})
            assert memo != given and Path(memo).name.startswith('loupe-test-view-memo-')
    finally:
        link.unlink()
