"""Corrections distinguish an absent amount from an omitted concurrency guard."""
import asyncio
from importlib import import_module
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from routers import financial


@pytest.mark.parametrize("model,extra", [(financial.UpdateAmountRequest, {"case_id": "case"}), (financial.BulkCorrectionItem, {"node_key": "record"})])
def test_explicit_absence_is_a_guard_and_cannot_conflict_with_a_number(model, extra):
    values = dict(new_amount=120, correction_reason="Checked original", **extra)
    assert "expected_raw_amount" not in model(**values).model_fields_set
    assert "expected_raw_amount" in model(**values, expected_raw_amount=None).model_fields_set
    with pytest.raises(ValueError):
        model(**values, expected_amount=0, expected_raw_amount=None)


@pytest.mark.parametrize("current,refused", [(None, False), ("", True), ("not stated", True), (0, True), (120, True)])
def test_absent_amount_is_compared_exactly_inside_the_write_lock(current, refused):
    module = import_module("services.neo4j.financial_service")
    driver = MagicMock(); tx = MagicMock()
    tx.run.return_value.single.side_effect = [{"amount": current}, {"key": "r", "amount": 120, "original_amount": None}]
    driver.session.return_value.__enter__.return_value.execute_write.side_effect = lambda callback: callback(tx)
    with patch.object(module, "driver", driver):
        if refused:
            with pytest.raises(ValueError):
                module.FinancialService().update_transaction_amount("r", "case", 120, "Checked", expected_raw_amount=None)
            assert tx.run.call_count == 1
        else:
            result = module.FinancialService().update_transaction_amount("r", "case", 120, "Checked", expected_raw_amount=None)
            assert result["original_amount"] is None and result["original_amount_raw"] is None


def test_individual_route_passes_explicit_null_and_reports_a_stale_value_as_conflict():
    request = financial.UpdateAmountRequest(case_id="case", new_amount=120, correction_reason="Checked", expected_raw_amount=None)
    with patch.object(financial.neo4j_service, "update_transaction_amount", side_effect=ValueError("changed")) as write:
        with pytest.raises(HTTPException) as error:
            asyncio.run(financial.update_transaction_amount("r", request))
        assert error.value.status_code == 409
        assert "expected_raw_amount" in write.call_args.kwargs and write.call_args.kwargs["expected_raw_amount"] is None


@pytest.mark.parametrize("raw,amount,refused", [(None, None, False), ("not stated", None, True), ("120", 120, True)])
def test_file_correction_checks_explicit_absence_before_any_writes(raw, amount, refused):
    request = financial.BulkCorrectRequest(case_id="case", corrections=[dict(node_key="r", new_amount=120, correction_reason="Checked", expected_raw_amount=None)])
    with patch.object(financial.neo4j_service, "get_financial_transactions", return_value={"transactions": [{"key": "r", "amount": amount, "raw_amount": raw}]}), patch.object(financial.neo4j_service, "update_transaction_amount", return_value={"success": True, "key": "r", "amount": 120}) as write:
        if refused:
            with pytest.raises(HTTPException) as error:
                asyncio.run(financial.bulk_correct_transactions(request))
            assert error.value.status_code == 409
            write.assert_not_called()
        else:
            result = asyncio.run(financial.bulk_correct_transactions(request))
            assert result["results"][0]["old_raw_amount"] is None
            assert "expected_raw_amount" in write.call_args.kwargs and write.call_args.kwargs["expected_raw_amount"] is None
