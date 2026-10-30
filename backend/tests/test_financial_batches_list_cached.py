"""The statement batch list is a cached view: computed once per state of the rows it reads (d5b330d1: 10-39 s on
every call before). Its result depends only on database rows and its case (no clock, files or graph), which is what
cached_view requires; equality with the uncached route was checked on six cases under one snapshot."""
from routers import financial_statement_import


def test_the_batch_list_is_served_by_the_view_cache():
    route = financial_statement_import.list_financial_batches
    assert route.__code__.co_filename.endswith('services/financial/view_cache.py')
    assert route.__wrapped__.__code__.co_filename.endswith('routers/financial_statement_import.py')


def test_the_batch_list_is_registered_cached_at_its_path():
    endpoints = {route.path: route.endpoint for route in financial_statement_import.router.routes
                 if 'GET' in getattr(route, 'methods', ())}
    path = next(path for path in endpoints if path.endswith('/batches/list'))
    assert endpoints[path] is financial_statement_import.list_financial_batches
    assert hasattr(endpoints[path], '__wrapped__')


def test_a_list_without_its_send_sources_is_answered_but_not_kept(monkeypatch):
    """A failed send-source lookup gives the list without them, as before, and marks the answer not to be kept by the
    view cache, so the next call looks the sources up again."""
    import services.activity_trail

    def failing(*args, **kwargs):
        raise RuntimeError('synthetic lookup failure')
    marked = []
    monkeypatch.setattr(services.activity_trail, 'batch_sources', failing)
    monkeypatch.setattr(financial_statement_import, 'not_kept', lambda: marked.append(True))
    monkeypatch.setattr(financial_statement_import.import_batches, 'available_batch_references', lambda *a: {})

    class NoBatches:
        def scalars(self, statement):
            return []
    case = '00000000-0000-0000-0000-000000000001'
    result = financial_statement_import.list_financial_batches.__wrapped__(case_id=case, db=NoBatches())
    assert result == dict(case_id=case, batches=[])
    assert marked == [True]
