"""Graph reads finish reading before converting, retry a time-limit end once,
and a route answers a timed-out read with a logged, plain 503."""

import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from neo4j.exceptions import ClientError

from routers import financial
# The package re-exports a `driver` object under the module's name.
neo4j_driver = importlib.import_module("services.neo4j.driver")
from services.neo4j.financial_service import FinancialService


def _timeout_error():
    err = ClientError("The transaction has been terminated.")
    err.code = "Neo.ClientError.Transaction.TransactionTimedOutClientConfiguration"
    return err


class _Rows:
    """A result that records how far it had been read when each row was handed out."""

    def __init__(self, rows, log):
        self._rows = rows
        self._log = log

    def __iter__(self):
        for i, row in enumerate(self._rows):
            self._log.append(("read", i))
            yield row
        self._log.append(("closed", len(self._rows)))


class _Session:
    def __init__(self, outcomes, log=None):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.log = log if log is not None else []

    def run(self, query, **params):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _Rows(outcome, self.log)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ReadAllRowsTests(unittest.TestCase):
    def test_reads_every_row(self):
        session = _Session([[{"k": 1}, {"k": 2}, {"k": 3}]])
        self.assertEqual(neo4j_driver.read_all_rows(session, "Q"), [{"k": 1}, {"k": 2}, {"k": 3}])

    def test_time_limit_end_is_retried_once(self):
        session = _Session([_timeout_error(), [{"k": 1}]])
        self.assertEqual(neo4j_driver.read_all_rows(session, "Q"), [{"k": 1}])
        self.assertEqual(session.calls, 2)

    def test_second_time_limit_end_is_raised(self):
        session = _Session([_timeout_error(), _timeout_error(), [{"k": 1}]])
        with self.assertRaises(ClientError):
            neo4j_driver.read_all_rows(session, "Q")
        self.assertEqual(session.calls, 2)

    def test_other_errors_are_not_retried(self):
        session = _Session([ValueError("bad"), [{"k": 1}]])
        with self.assertRaises(ValueError):
            neo4j_driver.read_all_rows(session, "Q")
        self.assertEqual(session.calls, 1)


class TransactionsReadBeforeConvertTests(unittest.TestCase):
    def test_all_rows_are_read_before_the_first_conversion(self):
        log = []
        row = {
            "key": "t1", "name": "T", "type": "FinancialTransaction", "date": "2024-01-02", "time": None,
            "amount": 5.0, "raw_amount": "5.00", "currency": "USD", "summary": None, "financial_category": None,
            "purpose": None, "counterparty_details": None, "notes": None, "from_entity_key": None,
            "from_entity_name": None, "to_entity_key": None, "to_entity_name": None, "prop_sender": None,
            "prop_receiver": None, "rel_to_key": None, "rel_to_name": None, "rel_from_key": None,
            "rel_from_name": None, "rf_key": None, "rf_name": None, "initiator_key": None,
            "initiator_name": None, "is_parent": False, "parent_transaction_key": None,
            "amount_corrected": False, "original_amount": None, "correction_reason": None,
            "financial_record_kind": "transaction", "financial_view_mode": "transaction",
            "is_financial_event": True, "is_evidence_backed_transaction": True, "evidence_strength": None,
            "evidence_source_type": None, "source_document_id": None, "source_filename": None,
            "source_page": None, "source_excerpt": None, "extraction_confidence": None,
        }
        rows = [dict(row, key=f"t{i}") for i in range(3)]
        meta = [{"total_amount_nodes": 3, "tagged_amount_nodes": 3}]

        class _MetaResult:
            def single(self):
                return meta[0]

        session = _Session([rows], log)
        real_run = session.run

        def run(query, **params):
            if "total_amount_nodes" in query:
                return _MetaResult()
            return real_run(query, **params)

        session.run = run
        service = FinancialService()
        original = service._record_to_transaction

        def convert(record, **kw):
            log.append(("convert", record["key"]))
            return original(record, **kw)

        service._record_to_transaction = convert
        with patch("services.neo4j.financial_service.driver") as drv, patch(
            "services.neo4j.financial_service.financial_graph_reads",
            SimpleNamespace(read=lambda session, key, compute: compute()),
        ):
            drv.session.return_value = session
            result = service.get_financial_transactions(case_id="c")
        self.assertEqual(result["total"], 3)
        first_convert = next(i for i, e in enumerate(log) if e[0] == "convert")
        closed = next(i for i, e in enumerate(log) if e[0] == "closed")
        self.assertLess(closed, first_convert)


class RouteAnswerTests(unittest.TestCase):
    def test_entities_time_limit_is_a_logged_503(self):
        with patch.object(financial.neo4j_service, "get_financial_entities", side_effect=_timeout_error()):
            with self.assertLogs(financial.logger, level="ERROR") as logs:
                with self.assertRaises(HTTPException) as caught:
                    financial.get_financial_entities(case_id="case-1")
        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("try again", caught.exception.detail)
        self.assertIn("case-1", logs.output[0])

    def test_transactions_time_limit_is_a_logged_503(self):
        with patch.object(financial.neo4j_service, "get_financial_transactions", side_effect=_timeout_error()):
            with self.assertLogs(financial.logger, level="ERROR"):
                with self.assertRaises(HTTPException) as caught:
                    financial.get_financial_transactions(
                        case_id="case-1", mode="transactions", types=None,
                        start_date=None, end_date=None, categories=None, db=None,
                    )
        self.assertEqual(caught.exception.status_code, 503)

    def test_other_failures_stay_500_and_are_logged(self):
        with patch.object(financial.neo4j_service, "get_financial_entities", side_effect=RuntimeError("boom")):
            with self.assertLogs(financial.logger, level="ERROR"):
                with self.assertRaises(HTTPException) as caught:
                    financial.get_financial_entities(case_id="case-1")
        self.assertEqual(caught.exception.status_code, 500)
        self.assertEqual(caught.exception.detail, "boom")


if __name__ == "__main__":
    unittest.main()


class WholeResultSessionTests(unittest.TestCase):
    """Live d5b330d1: a worker busy elsewhere converted the 27,926 rows so slowly that the server's
    25 s limit ended the read while rows were still arriving; fetched whole, the server is done at once."""

    def test_financial_reads_ask_for_the_whole_result_at_once(self):
        module = importlib.import_module("services.neo4j.financial_service")
        from services.neo4j.graph_read_cache import financial_graph_reads
        opened = []

        class Session:
            def __init__(self, **kwargs):
                opened.append(kwargs)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with patch.object(module.driver, "session", side_effect=lambda **kw: Session(**kw)), \
                patch.object(financial_graph_reads, "read", lambda session, key, compute: None):
            FinancialService().get_financial_transactions("case")
            FinancialService().get_financial_entities("case")
        self.assertEqual(opened, [{"fetch_size": neo4j_driver.WHOLE_RESULT}] * 2)
        self.assertEqual(neo4j_driver.WHOLE_RESULT, -1)
