"""The backend tests never use a real saved-views directory (tests/__init__.py)."""
import os
import tempfile
from pathlib import Path


def test_the_saved_views_directory_of_a_test_run_is_its_own_temporary_one():
    import tests  # noqa: F401 - the package sets it
    from services.financial import view_cache
    memo = view_cache._memo_dir()
    assert memo is not None
    assert Path.home() / '.cache' not in memo.parents
    assert Path(tempfile.gettempdir()) in memo.parents
    assert memo.name.startswith('loupe-test-view-memo-')
    assert os.environ['FINANCIAL_VIEW_MEMO_DIR'] == str(memo)
