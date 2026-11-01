"""Execute the real preflight handler without unrelated router startup imports.

Only case access and file classification are mocked. The endpoint body is
compiled from its source so undefined globals and validation failures execute.
This keeps the regression runnable on Windows despite Linux-only imports in
the wider financial package.
"""

import ast
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, status
from fastapi.concurrency import run_in_threadpool


@pytest.fixture
def endpoint(monkeypatch):
    source = Path(__file__).parents[1] / "routers" / "evidence.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    handler = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and any(
            isinstance(decorator, ast.Call)
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
            and decorator.args[0].value == "/route-check"
            for decorator in node.decorator_list
        )
    )
    handler.decorator_list = []
    handler.args.defaults = []
    for arg in handler.args.args:
        arg.annotation = None
    handler.returns = None

    case_service = ModuleType("services.case_service")
    case_service.check_case_access = Mock()
    case_service.CaseNotFound = type("CaseNotFound", (Exception,), {})
    case_service.CaseAccessDenied = type("CaseAccessDenied", (Exception,), {})
    classifier = ModuleType("services.financial.route_check")
    classifier.check_case_files = Mock(
        side_effect=lambda db, **kwargs: [
            SimpleNamespace(as_dict=lambda fid=fid: {"file_id": str(fid)})
            for fid in kwargs["file_ids"]
        ]
    )
    classifier.summarise = lambda checks: {"checked": len(checks)}
    monkeypatch.setitem(sys.modules, "services.case_service", case_service)
    monkeypatch.setitem(sys.modules, "services.financial.route_check", classifier)
    namespace = {
        "UUID": UUID,
        "HTTPException": HTTPException,
        "status": status,
        "run_in_threadpool": run_in_threadpool,
        "_resolve_stored_path": Mock(),
        "_phone_container_ids": Mock(return_value=set()),
    }
    exec(compile(ast.Module(body=[handler], type_ignores=[]), str(source), "exec"), namespace)
    namespace[handler.name].namespace = namespace
    return namespace[handler.name], case_service, classifier


@pytest.mark.asyncio
async def test_a_phone_report_in_the_selection_is_answered_as_not_a_bank_file_and_the_others_are_checked(endpoint):
    """A phone report row is never opened by this check and never takes the other files' answers away: it is
    answered as not a bank file (processing then skips it), and every other id is classified as before."""
    handler, access, classifier = endpoint
    phone_id, other_ids = uuid4(), [uuid4(), uuid4()]
    handler.namespace["_phone_container_ids"] = Mock(return_value={phone_id})
    statement = Mock()
    statement.where.return_value = statement
    handler.namespace["select"] = Mock(return_value=statement)
    handler.namespace["EvidenceFile"] = SimpleNamespace(id=Mock(), original_filename=Mock())
    classifier.check_case_files.side_effect = lambda db, **kwargs: [
        SimpleNamespace(file_id=str(fid), as_dict=lambda fid=fid: {"file_id": str(fid), "outcome": "native"})
        for fid in kwargs["file_ids"]
    ]
    classifier.FileRouteCheck = lambda file_id, file_name: SimpleNamespace(
        file_id=file_id, as_dict=lambda: {"file_id": file_id, "file_name": file_name, "outcome": "not_native"})
    db = SimpleNamespace(execute=lambda q: SimpleNamespace(all=lambda: [(phone_id, "Phone report.zip")]))
    ids = [str(other_ids[0]), str(phone_id), str(other_ids[1])]
    result = await handler(SimpleNamespace(case_id=str(uuid4()), file_ids=ids), object(), db)
    assert [(f["file_id"], f["outcome"]) for f in result["files"]] == [
        (ids[0], "native"), (ids[1], "not_native"), (ids[2], "native")]
    assert classifier.check_case_files.call_args.kwargs["file_ids"] == other_ids
    assert result["files"][1]["file_name"] == "Phone report.zip"


@pytest.mark.asyncio
@pytest.mark.parametrize("file_count", [1, 51, 250])
async def test_preflight_accepts_selections_without_removed_constant(endpoint, file_count):
    handler, access, classifier = endpoint
    case_id = str(uuid4())
    file_ids = [str(uuid4()) for _ in range(file_count)]
    db, user = object(), object()
    result = await handler(SimpleNamespace(case_id=case_id, file_ids=file_ids), user, db)

    assert result["summary"]["checked"] == file_count
    assert [item["file_id"] for item in result["files"]] == file_ids
    access.check_case_access.assert_called_once_with(
        db, UUID(case_id), user, required_permission=("case", "view")
    )
    assert classifier.check_case_files.call_args.kwargs["file_ids"] == list(map(UUID, file_ids))


@pytest.mark.asyncio
@pytest.mark.parametrize("file_ids", [[], ["invalid-file-id"]])
async def test_preflight_still_rejects_invalid_selections(endpoint, file_ids):
    handler, _, classifier = endpoint
    with pytest.raises(HTTPException) as error:
        await handler(SimpleNamespace(case_id=str(uuid4()), file_ids=file_ids), object(), object())
    assert error.value.status_code == 400
    classifier.check_case_files.assert_not_called()


@pytest.mark.asyncio
async def test_preflight_still_rejects_case_access_denial(endpoint):
    handler, access, classifier = endpoint
    access.check_case_access.side_effect = access.CaseAccessDenied("Access denied")
    with pytest.raises(HTTPException) as error:
        await handler(SimpleNamespace(case_id=str(uuid4()), file_ids=[str(uuid4())]), object(), object())
    assert error.value.status_code == 403
    classifier.check_case_files.assert_not_called()
