"""Check dossier request contracts without importing unrelated platform routers."""
import ast
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, Field, ValidationError


@pytest.fixture(scope="module")
def contracts():
    path = Path(__file__).parents[1] / "routers/dossiers.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    definitions = [node for node in tree.body if isinstance(node, ast.ClassDef) or isinstance(node, ast.FunctionDef) and node.name == "_payload"]
    namespace = {"BaseModel": BaseModel, "Field": Field, "Any": Any, "UUID": UUID, "date": date, "datetime": datetime}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


@pytest.mark.parametrize("value", [None, "2025", "2025-07", "2025-07-23", "2025-07-23T16:00:00Z"])
def test_partial_dates_reach_service_without_a_fabricated_timestamp(contracts, value):
    request = contracts["InterviewUpdate"](date_value=value)
    assert contracts["_payload"](request, exclude_unset=True) == {"date_value": value}


def test_old_timestamp_requests_and_unrelated_edits_stay_compatible(contracts):
    request = contracts["InterviewCreate"](interview_date="2025-07-23T16:00:00Z")
    payload = contracts["_payload"](request)
    assert payload["interview_date"].year == 2025 and payload["date_value"] is None
    update = contracts["DossierUpdate"](summary="A revised brief")
    assert contracts["_payload"](update, exclude_unset=True) == {"summary": "A revised brief"}


def test_contact_contract_accepts_source_ids_and_ignores_spoofed_attribution(contracts):
    evidence_id = uuid4()
    request = contracts["DossierUpdate"](contacts=[{"kind": "phone", "value": "+1 555 0100", "evidence_file_id": str(evidence_id), "recorded_by_user_id": str(uuid4())}])
    contact = contracts["_payload"](request, exclude_unset=True)["contacts"][0]
    assert contact["evidence_file_id"] == evidence_id
    assert "recorded_by_user_id" not in contact


@pytest.mark.parametrize("contact", [{"kind": "secret", "value": "test"}, {"kind": "phone", "value": ""}, {"kind": "phone", "value": "test", "evidence_file_id": "not-an-id"}])
def test_contact_contract_rejects_invalid_details(contracts, contact):
    with pytest.raises(ValidationError):
        contracts["DossierUpdate"](contacts=[contact])


def test_contact_lists_are_bounded(contracts):
    with pytest.raises(ValidationError):
        contracts["DossierUpdate"](contacts=[{"kind": "phone", "value": "test"}] * 101)
