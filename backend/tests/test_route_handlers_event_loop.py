"""Route handlers declared async that never await run their blocking work on the worker's event loop: every other
request in that worker, Financial pages included, waits for them. Measured 2026-10-30 (request_speed_hourly, 7 days):
16 such handlers in use held the loop for 1,268 s, e.g. an assistant message 85 s, sign-in password hashing 2.2 s on
average. Those are plain functions now (FastAPI runs them in its thread pool), and so are 187 of the 189 others that
were async without an await; the two that must stay async (a streaming answer that watches for the client leaving,
and a chunked upload whose cache a loop task sweeps) await their blocking calls in the thread pool."""
import ast
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[1]

# Empty since 2026-10-30 (fin-eventloop): every route handler that does blocking work is a plain function (run in
# the thread pool) or awaits it off the loop (run_in_threadpool). A handler declared async without an await fails
# the test below; make it a plain function instead.
NOT_YET_CONVERTED = set()


def _blocking_async_handlers():
    found = set()
    for path in sorted((BACKEND / 'routers').rglob('*.py')):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if not any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                       and d.func.attr in ('get', 'post', 'put', 'patch', 'delete') for d in node.decorator_list):
                continue

            def awaits(n):
                for child in ast.iter_child_nodes(n):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                        continue
                    if isinstance(child, (ast.Await, ast.AsyncFor, ast.AsyncWith)) or awaits(child):
                        return True
                return False
            if not awaits(node):
                found.add(f'{path.relative_to(BACKEND).as_posix()}:{node.name}')
    return found


def test_no_new_route_handler_blocks_the_event_loop():
    # Equal, not a subset: a converted handler leaves the list in the same change, so the list only shrinks.
    assert _blocking_async_handlers() == NOT_YET_CONVERTED


def test_the_handlers_measured_in_use_run_in_the_thread_pool():
    measured = {'routers/auth.py:login', 'routers/agent.py:create_agent_message', 'routers/chat.py:get_suggestions',
                'routers/evidence.py:get_evidence_file', 'routers/workspace.py:get_case_context',
                'routers/agent.py:list_agent_threads', 'routers/snapshots.py:list_snapshots',
                'routers/background_tasks.py:list_tasks', 'routers/llm_config.py:get_available_models',
                'routers/evidence_folders.py:get_folder_contents', 'routers/evidence_folders.py:get_folder_tree',
                'routers/agent.py:get_agent_thread', 'routers/workspace.py:list_mandate_versions',
                'routers/chat_history.py:list_chat_histories', 'routers/evidence.py:get_evidence_by_filename',
                'routers/financial_ledger.py:get_ledger_sources'}
    assert not measured & _blocking_async_handlers()
    assert not measured & NOT_YET_CONVERTED
    for entry in measured:  # each still exists, as a plain function
        path, name = entry.split(':')
        tree = ast.parse((BACKEND / path).read_text())
        assert any(isinstance(node, ast.FunctionDef) and node.name == name for node in ast.walk(tree)), entry


# Async handlers and async dependencies that take a sync database session must not use it on the event loop: every
# call that touches the session (or Neo4j) runs through run_in_threadpool / anyio.to_thread. Awaiting a coroutine
# that is handed the session counts as touching it (the coroutine runs on the loop). Measured 2026-10-31
# (perf-analysis lens-evidence): the engine jobs poll held a worker's loop 5-19 s this way. Each remaining entry is
# work in progress for fin-eventloop item A2(b), with the reason it is not converted yet.
NOT_YET_OFFLOADED = {
    # Upload, folder-processing, deletion and Financial send actions: database work around engine calls on the
    # shared async engine client, still on the loop in the handler itself; next in A2(b).
    'routers/evidence.py:upload_evidence', 'routers/evidence.py:process_cellebrite_folder',
    'routers/financial_statement_import.py:prepare_existing',
}

_OFFLOAD = {'run_in_threadpool', 'to_thread', 'run_sync'}
# Coroutines that take the session but run their own database work in the thread pool.
_OFFLOADS_INTERNALLY = {'reconcile_job_by_id', 'reconcile_case_jobs', 'process_db_files', 'retry_file_checked',
                        # reads the graph with asyncio.to_thread, then compares names between awaits
                        'find_similar_entities_streaming'}
_ROUTE_METHODS = ('get', 'post', 'put', 'patch', 'delete', 'api_route')


def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _dotted(node.value) + '.' + node.attr
    return '?'


def _is_route(node):
    return any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in _ROUTE_METHODS
               for d in node.decorator_list)


def _async_functions_using_a_sync_session_on_the_loop():
    """Route handlers and async dependencies (named in Depends(...), or built by a *_dependency factory) that call
    the database or Neo4j on the event loop. Async functions nested in a handler count for it; nested plain
    functions do not (they are what gets handed to the thread pool)."""
    found = {}
    for path in sorted((BACKEND / 'routers').rglob('*.py')):
        tree = ast.parse(path.read_text())
        dependency_names = {call.args[0].id for call in ast.walk(tree)
                            if isinstance(call, ast.Call) and _dotted(call.func) == 'Depends'
                            and call.args and isinstance(call.args[0], ast.Name)}
        candidates = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.endswith('_dependency'):
                candidates += [n for n in ast.walk(node) if isinstance(n, ast.AsyncFunctionDef)]
            if isinstance(node, ast.AsyncFunctionDef) and (_is_route(node) or node.name in dependency_names):
                candidates.append(node)
        for node in candidates:
            sessions = {a.arg for a in node.args.args + node.args.kwonlyargs
                        if a.annotation is not None and 'Session' in ast.unparse(a.annotation)
                        and 'Async' not in ast.unparse(a.annotation)}
            hits = []

            def visit(n, offloaded=False):
                for child in ast.iter_child_nodes(n):
                    if isinstance(child, (ast.FunctionDef, ast.Lambda)):
                        continue
                    if isinstance(child, ast.Call):
                        name = _dotted(child.func)
                        short = name.split('.')[-1]
                        off = offloaded or short in _OFFLOAD or short in _OFFLOADS_INTERNALLY
                        passed = list(child.args) + [k.value for k in child.keywords]
                        if not off and (name.split('.')[0] in sessions or 'neo4j' in name.lower()
                                        or any(isinstance(a, ast.Name) and a.id in sessions for a in passed)):
                            hits.append(f'{child.lineno}:{name}')
                        visit(child, off)
                        continue
                    visit(child, offloaded)
            visit(node)
            if hits:
                found[f'{path.relative_to(BACKEND).as_posix()}:{node.name}'] = hits
    return found


def test_no_async_handler_or_dependency_uses_a_sync_session_on_the_event_loop():
    found = _async_functions_using_a_sync_session_on_the_loop()
    # Equal, not a subset: an entry leaves the list in the change that converts it.
    assert set(found) == NOT_YET_OFFLOADED, {k: v for k, v in found.items() if k not in NOT_YET_OFFLOADED}


def test_the_router_wide_access_checks_and_the_jobs_poll_stay_off_the_event_loop():
    found = _async_functions_using_a_sync_session_on_the_loop()
    for entry in ('routers/case_access.py:require_request_case_access',
                  'routers/evidence.py:_require_evidence_object_access', 'routers/evidence.py:list_engine_jobs',
                  'routers/evidence.py:get_engine_job', 'routers/evidence_uploads.py:put_chunk'):
        assert entry not in found
