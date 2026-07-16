# DKT-445 Notebook Permissions, Filters, and Rollback Evidence

Verification timestamp: 2026-07-16T18:15:14Z

## Result

Pass. No unexplained mismatches, failed thresholds, or new blocking tickets were identified for DKT-445.

## Commands Run

The local shell did not have `pytest` or backend dependencies installed, so verification used a temporary virtual environment at `/tmp/dkt445-venv`. The environment installed `backend/requirements.txt` with `openai-whisper` excluded to avoid pulling the large torch/CUDA dependency chain that is not exercised by these backend tests, plus `pytest`.

```bash
/tmp/dkt445-venv/bin/python -m pytest backend/tests/test_notebook_permissions.py backend/tests/test_notebook_filters_and_rollback.py backend/tests/test_notebook_service.py -v
```

Result: 13 passed, 8 warnings.

```bash
/tmp/dkt445-venv/bin/python -m pytest backend/tests/test_notebook_filters_and_rollback.py -q
```

Result: 4 passed, 8 warnings.

```bash
/tmp/dkt445-venv/bin/python -m pytest backend/tests/test_notebook_filters_and_rollback.py -q
```

Result: 4 passed, 8 warnings.

```bash
/tmp/dkt445-venv/bin/python -m pytest backend/tests -q
```

Result: 129 passed, 8 warnings.

Warnings were pre-existing deprecation warnings from Pydantic `Config`, FastAPI `regex`, and a Neo4j driver destructor warning. They did not indicate DKT-445 verification failure.

## Acceptance Criteria Traceability

| DKT-445 requirement | Evidence |
| --- | --- |
| Case/user permissions are enforced. | `backend/tests/test_notebook_permissions.py::NotebookPermissionRouterTests::test_non_member_is_denied_for_all_notebook_endpoints`; `test_viewer_can_list_but_cannot_mutate_notes`; `test_member_without_case_permissions_is_denied`; `test_editor_can_create_update_and_delete_notes`; `test_super_admin_can_access_case_without_membership`. |
| List filters are case-scoped and correct. | `backend/tests/test_notebook_filters_and_rollback.py::NotebookFilterTests::test_list_notes_filters_by_case_author_search_and_link`. |
| Cross-case notes remain hidden and cannot be mutated through the wrong case. | `backend/tests/test_notebook_permissions.py::NotebookPermissionRouterTests::test_note_id_from_another_case_is_not_mutated_through_current_case`; `backend/tests/test_notebook_filters_and_rollback.py::NotebookFilterTests::test_link_filter_cannot_leak_note_from_another_case`. |
| Failed saves roll back without partial note/link/log rows. | `backend/tests/test_notebook_filters_and_rollback.py::NotebookRollbackRouterTests::test_failed_create_rolls_back_uncommitted_note_link_and_log`. |
| Failed updates preserve original content and avoid duplicate links. | `backend/tests/test_notebook_filters_and_rollback.py::NotebookRollbackRouterTests::test_failed_update_restores_original_note_and_does_not_duplicate_links`. |

## Code Paths Verified

- `backend/routers/notebook.py` gates list/target endpoints through case view permission and create/update/delete through case edit permission.
- `backend/services/case_service.py` enforces membership permissions while allowing super-admin bypass.
- `backend/services/notebook_service.py` scopes note lookup and list queries to `NotebookNote.case_id == case_id` and `deleted_at.is_(None)`.
- `backend/postgres/session.py` rolls back request sessions on exceptions and before close when a transaction remains open.

Concurrency, refresh/restart, and multi-worker behavior remain scoped to sibling ticket DKT-446.
