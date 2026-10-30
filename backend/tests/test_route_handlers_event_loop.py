"""Route handlers declared async that never await run their blocking work on the worker's event loop: every other
request in that worker, Financial pages included, waits for them. Measured 2026-10-30 (request_speed_hourly, 7 days):
16 such handlers in use held the loop for 1,268 s, e.g. an assistant message 85 s, sign-in password hashing 2.2 s on
average. Those are plain functions now (FastAPI runs them in its thread pool). The handlers below are still async
without an await and were not seen in use in those 7 days; this list may only shrink."""
import ast
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[1]

NOT_YET_CONVERTED = {
    'routers/auth.py:change_password',
    'routers/backfill.py:backfill_embeddings',
    'routers/backfill.py:backfill_chunks',
    'routers/backfill.py:backfill_entity_metadata',
    'routers/backfill.py:backfill_document_summaries_endpoint',
    'routers/backfill.py:backfill_case_ids_endpoint',
    'routers/backfill.py:get_backfill_status',
    'routers/chat.py:chat',
    'routers/chat.py:extract_nodes_from_answer',
    'routers/database.py:list_entities_status',
    'routers/database.py:list_entities',
    'routers/database.py:get_entity',
    'routers/llm_config.py:get_current_config',
    'routers/llm_config.py:set_llm_config',
    'routers/llm_config.py:get_confidence_threshold',
    'routers/llm_config.py:set_confidence_threshold',
    'routers/maintenance.py:health_check',
    'routers/maintenance.py:run_audit',
    'routers/maintenance.py:run_repair',
    'routers/maintenance.py:purge_orphans',
    'routers/profiles.py:list_profiles',
    'routers/profiles.py:get_profile',
    'routers/profiles.py:create_or_update_profile',
    'routers/profiles.py:delete_profile',
    'routers/query.py:execute_cypher',
    'routers/system_logs.py:get_logs',
    'routers/system_logs.py:get_log_statistics',
    'routers/system_logs.py:clear_logs',
    'routers/timeline.py:get_timeline',
    'routers/timeline.py:get_event_types',
    'routers/workspace.py:update_case_context',
    'routers/workspace.py:create_mandate_version',
}


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
