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
