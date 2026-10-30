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
