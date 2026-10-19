"""Exercise request models without importing unrelated ingestion/Agent runtimes."""
import ast
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import BaseModel, Field, ValidationError


def model(filename, names):
    tree = ast.parse((Path(__file__).parents[1] / "routers" / filename).read_text(encoding="utf8"))
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in names]
    namespace = {"BaseModel": BaseModel, "Field": Field, "Any": Any, "FindingSignificance": Literal["high", "medium", "low"]}
    exec(compile(ast.Module(body=classes, type_ignores=[]), filename, "exec"), namespace)
    return namespace


def test_significance_clear_must_be_explicit_and_remains_enum_validated():
    request = model("workspace_entries.py", {"EntrySignificanceRequest"})["EntrySignificanceRequest"]
    assert request(expected_version=1, significance=None).significance is None
    with pytest.raises(ValidationError):
        request(expected_version=1)
    with pytest.raises(ValidationError):
        request(expected_version=1, significance="automatic")


def test_theory_conversion_can_start_unrated():
    request = model("workspace_entries.py", {"EntryVersionRequest", "TheoryConversionRequest"})["TheoryConversionRequest"]
    assert request(expected_version=1).significance is None


def test_partial_context_requests_preserve_omitted_fields_and_template_drafts():
    request = model("workspace.py", {"CaseContextUpdate"})["CaseContextUpdate"]
    assert request(case_summary="New summary").model_dump(exclude_unset=True) == {"case_summary": "New summary"}
    payload = request(template_values={"criminal_defense": {"charges": "New charge"}}).model_dump(exclude_unset=True)
    assert payload == {"template_values": {"criminal_defense": {"charges": "New charge"}}}
