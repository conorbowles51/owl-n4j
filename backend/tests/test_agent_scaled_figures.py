"""A payment amount stated 10x or 100x its record (BNB2 run 59672695 replays, 11 Nov 2026).

Two parts: the model reads a readable amount beside each minor-unit figure (model_payloads.with_readable_amounts),
and an answer figure 10x or 100x the payment it cites is listed under the answer with the record's own amount
(wrap_up.check_scaled_figures). The sentences below are from the recorded answer.
"""
import os
import unittest
from unittest.mock import patch

from services.agent import wrap_up
from services.agent.lean_history import digest_payload
from services.agent.model_payloads import model_view, tool_message_payload

ROW = "2916660a-9f31-412a-ae3e-ec28c042164f"
OTHER = "0c2d21a3-0000-4000-8000-000000000001"
CASE = "d5b330d1-b3fe-4b03-8539-98d9cc3115e0"


def ledger_page():
    return {"schema": "loupe.agent.financial_ledger/1", "view": "transactions", "items": [
        {"cite": "txn://" + ROW, "amount_minor": "146353683", "running_balance_minor": "445770814",
         "currency": "MXN", "currency_exponent": 2, "transaction_date": "2024-09-05",
         "description": "SALDO ESCR CASA VILLA A1 PORTA FORTUNA"},
        {"cite": "txn://" + OTHER, "amount_minor": "21702500", "currency": "MXN", "currency_exponent": 2,
         "transaction_date": "2025-05-28"}]}


def views():
    return {"r1": model_view(ledger_page())}


class ReadableAmountTests(unittest.TestCase):
    def test_each_minor_figure_is_read_beside_its_amount(self):
        row = model_view(ledger_page())["data"]["items"][0]
        self.assertEqual(row["amount_minor"], "146353683")
        self.assertEqual(row["amount"], "MXN 1,463,536.83")
        self.assertEqual(row["running_balance"], "MXN 4,457,708.14")

    def test_the_tool_message_carries_the_amount(self):
        payload = tool_message_payload(result_id="r1", summary="s", data=ledger_page())
        self.assertEqual(payload["data"]["items"][1]["amount"], "MXN 217,025.00")

    def test_a_group_total_and_a_nested_record_without_its_own_currency(self):
        data = {"items": [{"currency": "JPY", "credits_minor": "1500", "debits_minor": 7, "net_minor": "-5",
                           "p3": {"paid_ab_minor": 1200}}]}
        item = model_view(data)["data"]["items"][0]
        self.assertEqual((item["credits"], item["debits"], item["net"]), ("JPY 1,500", "JPY 7", "JPY -5"))
        self.assertEqual(item["p3"]["paid_ab"], "JPY 1,200")

    def test_an_existing_field_no_currency_or_a_non_number_is_left_alone(self):
        data = {"a": {"currency": "MXN", "amount_minor": "100", "amount": "kept"},
                "b": {"amount_minor": "100"}, "c": {"currency": "MXN", "amount_minor": None, "x_minor": True},
                "d": {"currency": "ZZZ", "amount_minor": "100"}}
        view = model_view(data)["data"]
        self.assertEqual(view["a"]["amount"], "kept")
        self.assertNotIn("amount", view["b"])
        self.assertNotIn("amount", view["c"])
        self.assertNotIn("x", view["c"])
        self.assertNotIn("amount", view["d"])

    def test_a_digest_keeps_the_readable_group_totals(self):
        data = {"schema": "loupe.agent.financial_ledger/1", "view": "groups", "items": [
            {"group": "g", "currency": "MXN", "credits_minor": "100", "debits_minor": "0", "net_minor": "100"}]}
        payload = tool_message_payload(result_id="r1", summary="s", data=data)
        figure = digest_payload(payload)["facts"]["group_figures"][0]
        self.assertEqual(figure["credits"], "MXN 1.00")


class ScaledFigureTests(unittest.TestCase):
    def test_the_recorded_100x_figure_is_listed_with_the_record_amount(self):
        answer = ("- $146,353,683.00 del 05/09/2024 [txn://%s](txn://%s), [09-SEPT 24 INTERCAM MPA.pdf, p.2]"
                  "(doc://81cade47-0a38-4ee9-9814-68c6d67893ce/2)." % (ROW, ROW))
        text, found = wrap_up.check_scaled_figures(answer, views())
        self.assertEqual(found, [{"stated": "146,353,683.00", "link": "txn://" + ROW, "record": "MXN 1,463,536.83"}])
        self.assertTrue(text.startswith(answer))
        self.assertIn(wrap_up.SCALED_HEADING, text)
        self.assertIn("146,353,683.00 is written beside [this payment](txn://%s); its record says MXN 1,463,536.83."
                      % ROW, text)

    def test_a_10x_and_a_tenth_are_listed_too(self):
        self.assertEqual([f["stated"] for f in wrap_up.scaled_figures(
            "Pago de 14,635,368.30 [p](txn://%s). Otro de 21,702.50 [p](txn://%s)." % (ROW, OTHER), views())],
            ["14,635,368.30", "21,702.50"])

    def test_the_right_figure_a_date_a_reference_and_an_unlinked_sentence_are_not_listed(self):
        answer = ("El saldo de 1,463,536.83 del 05/09/2024, ref 146353683, [p](txn://%s).\n"
                  "Total 146,353,683.00 sin enlace." % ROW)
        self.assertEqual(wrap_up.check_scaled_figures(answer, views()), (answer, []))

    def test_a_figure_that_is_another_linked_payment_amount_is_not_listed(self):
        rows = {"r": {"data": {"items": [
            {"cite": "txn://a", "amount_minor": "100000", "currency": "MXN", "currency_exponent": 2},
            {"cite": "txn://b", "amount_minor": "10000000", "currency": "MXN", "currency_exponent": 2}]}}}
        self.assertEqual(wrap_up.scaled_figures("1,000.00 [x](txn://a) y 100,000.00 [y](txn://b)", rows), [])

    def test_every_answer_is_checked_whatever_the_fit_items(self):
        from services.agent.graph import _with_kept_sources
        from services.agent.tools import AgentToolContext
        context = AgentToolContext(case_id=CASE)
        context.model_views.update(views())
        answer = "Pagó 146,353,683.00 [p](txn://%s)." % ROW
        for items in ("W", ""):
            with patch.dict(os.environ, {"LOUPE_AGENT_FIT": items}):
                self.assertIn("its record says MXN 1,463,536.83", _with_kept_sources(answer, context, False))


if __name__ == "__main__":
    unittest.main()
