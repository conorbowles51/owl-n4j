"""Each cited sentence read against what it cites (lx-citeproof B): code first, one model call for the rest."""
import hashlib
import json
import uuid
from pathlib import Path

from postgres.base import Base
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
from postgres.models.runtime_state import AIModelPolicy  # read by services.ai_budget
from services import citation_support as S
from tests.test_agent_financial_ledger_tools import LedgerToolFixture

PAGE_1 = "Bay 4 lease. Tenant: Travis Kell. Landlord: Ruiz Auto & Tire. Gate at 39.288533, -76.623911."
PAGE_2 = "Rent: $650.00 a month, due on the 1st. Signed 1 October 2023 by Travis Kell and Mateo Ruiz."


class _Case(LedgerToolFixture):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[EvidenceDocumentText.__table__, AIModelPolicy.__table__])
        self.file = EvidenceFile(id=uuid.uuid4(), case_id=self.case.id, original_filename="lease.pdf",
                                 stored_path=f"/evidence/{uuid.uuid4()}", sha256="1" * 64)
        self.db.add(self.file)
        content = PAGE_1 + "\n" + PAGE_2
        a = len(PAGE_1)
        self.db.add(EvidenceDocumentText(
            evidence_file_id=self.file.id, content=content, content_sha256=hashlib.sha256(content.encode()).hexdigest(),
            character_count=len(content), source_locations=[
                {"kind": "page", "page_number": 1, "start_char": 0, "end_char": a},
                {"kind": "page", "page_number": 2, "start_char": a + 1, "end_char": len(content)}]))
        self.db.commit()
        self.p2 = f"doc://{self.file.id}/2"
        self.calls = []

    def judge(self, verdicts):
        def call(prompt):
            self.calls.append(prompt)
            items = json.loads(prompt.split("\n\n", 1)[1])["items"]
            return json.dumps({"items": [{"id": item["id"], "state": verdicts,
                                          "reason": "The page names the lease, not the keys."} for item in items]}), \
                {"prompt_tokens": 10, "completion_tokens": 5}, "m1"
        return call


class SupportTests(_Case):
    def test_a_sentence_whose_facts_are_on_the_cited_page_supports_and_one_whose_are_not_is_marked(self):
        answer = (f"Travis Kell pays $650 a month for bay 4 [lease, p.2]({self.p2}). "
                  f"Harold Vint paid $1,250 on 12 April 2024 [lease, p.2]({self.p2}).")
        marked, result = S.check_and_mark(self.db, self.case.id, answer, judge=self.judge("supports"))
        states = [c["citations"][0]["state"] for c in result["claims"]]
        self.assertEqual(states, [S.SUPPORTS, S.NOT_MENTIONED])
        self.assertEqual([c["citations"][0]["by"] for c in result["claims"]], ["code", "code"])
        self.assertEqual(self.calls, [])  # code settled both: no model call
        # the failing sentence is marked where it stands, the supported one is not
        self.assertIn(f"12 April 2024 [lease, p.2]({self.p2}). {S.MARK}", marked)
        self.assertNotIn(f"bay 4 [lease, p.2]({self.p2}). {S.MARK}", marked)
        self.assertIn("**Source check**: 1 of 2 citations support their sentence; 1 do not mention it.", marked)
        self.assertIn("1,250", marked.split("**Source check**")[1])
        self.assertTrue(marked.startswith(answer[:40]))  # the answer stays as written

    def test_what_code_cannot_settle_goes_to_the_model_in_one_call_and_is_shown_as_a_model_reading(self):
        answer = (f"Travis Kell signed the lease and holds the keys [p]({self.p2}).\n"
                  f"- The tenant is a known associate [p](doc://{self.file.id}/1).")
        marked, result = S.check_and_mark(self.db, self.case.id, answer, judge=self.judge("partly"))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual({c["citations"][0]["state"] for c in result["claims"]}, {S.PARTLY})
        self.assertEqual({c["citations"][0]["by"] for c in result["claims"]}, {"model:m1"})
        self.assertNotIn(S.MARK, marked)  # partly is not a failure
        self.assertIn("read by a model (m1), not by a person", marked)
        self.assertEqual(result["model"]["usage"], {"prompt_tokens": 10, "completion_tokens": 5})

    def test_a_sentence_citing_two_sources_gets_a_model_verdict_for_each(self):
        # live 15 Nov 2026: given one item per sentence with its sources listed, gpt-5-mini judged the first source
        # and skipped the rest (6 of 24 answered); each sentence-source pair is now its own item
        answer = f"The tenant holds the keys [a](doc://{self.file.id}/1) [b]({self.p2})."
        _, result = S.check_and_mark(self.db, self.case.id, answer, judge=self.judge("supports"))
        items = json.loads(self.calls[0].split("\n\n", 1)[1])["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual({type(item["source"]) for item in items}, {str})
        self.assertEqual({item["cites"] for item in items}, {2})  # each source may hold its share of the sentence
        self.assertEqual([c["by"] for c in result["claims"][0]["citations"]], ["model:m1", "model:m1"])
        self.assertEqual(result["model"]["sentences"], 1)

    def test_a_figure_the_source_holds_with_a_digit_changed_is_not_supported_whatever_the_model_says(self):
        # live 15 Nov 2026: gpt-5-mini quoted 39.288533 from the record and still said it supports 39.288503
        answer = f"The gate stands at 39.288503, -76.623911 [p](doc://{self.file.id}/1)."
        _, result = S.check_and_mark(self.db, self.case.id, answer, judge=self.judge("supports"))
        cite = result["claims"][0]["citations"][0]
        self.assertEqual((cite["state"], cite["by"]), (S.PARTLY, "code"))
        self.assertEqual(cite["reason"], "The source has 39.288533 where the sentence has 39.288503.")
        self.assertEqual(S.near_misses({"2024-05-04", "650"}, {"2024-05-03", "660"}), [])  # dates, short numbers

    def test_a_sentence_of_names_and_local_times_is_read_by_the_model_not_settled_by_code(self):
        # live 15 Nov 2026: "left a fixed point at 22:40 local time" against records holding 02:40 UTC was marked as
        # not mentioning it by code, without a model reading
        answer = f"Harold Vint left at 22:40 local time and was back by 23:20 [p]({self.p2})."
        _, result = S.check_and_mark(self.db, self.case.id, answer, judge=self.judge("supports"))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result["claims"][0]["citations"][0]["by"], "model:m1")

    def test_a_link_whose_text_states_the_fact_is_read_as_part_of_its_sentence(self):
        # live 15 Nov 2026: "- [2024-03-17, USD 1,200.00](txn://...) from [kell-2024-03.pdf, p.1](doc://...)" was read
        # as the sentence "from", which no source states
        answer = f"- [1 October 2023, $650.00]({self.p2}) from [lease.pdf, p.2]({self.p2})"
        found = S.claims(answer)
        self.assertEqual(found[0].plain, "1 October 2023, $650.00 from")
        for named in ("Phone 1 · Native Messages · Travis Kell", f"doc://{self.file.id}/2", "Phone 4 · Telegram · PTT-20240609"):
            self.assertEqual(S.claims(f"He wrote back [{named}]({self.p2}).")[0].plain, "He wrote back .")
        # a citation standing alone still backs the sentence before it, whatever its link says
        alone = S.claims(f"Travis Kell paid the rent. [message of 8 Jun 2024 17:50 UTC]({self.p2})")
        self.assertEqual([(c.plain, c.hrefs) for c in alone], [("Travis Kell paid the rent.", [self.p2])])
        result = S.check(self.db, self.case.id, answer, judge=None)
        self.assertEqual((result["claims"][0]["state"], result["claims"][0]["citations"][0]["by"]), (S.SUPPORTS, "code"))

    def test_many_citations_go_to_the_model_in_concurrent_chunks_and_a_failed_chunk_is_named(self):
        answer = "\n".join(f"Nobody {i} holds the keys [p]({self.p2})." for i in range(23))
        good = self.judge("supports")

        def judge(prompt):
            items = json.loads(prompt.split("\n\n", 1)[1])["items"]
            if items[0]["id"] == S.CHUNK_ITEMS:
                raise TimeoutError("slow")
            return good(prompt)
        result = S.check(self.db, self.case.id, answer, judge=judge)
        chunks = -(-23 // S.CHUNK_ITEMS)
        self.assertEqual(sum(len(json.loads(p.split("\n\n", 1)[1])["items"]) for p in self.calls), 23 - S.CHUNK_ITEMS)
        self.assertTrue(all(len(json.loads(p.split("\n\n", 1)[1])["items"]) <= S.CHUNK_ITEMS for p in self.calls))
        self.assertEqual((result["model"]["calls"], result["model"]["failed_calls"]), (chunks, 1))
        states = [c["citations"][0]["state"] for c in result["claims"]]
        self.assertEqual(states.count(S.SUPPORTS), 23 - S.CHUNK_ITEMS)
        self.assertEqual({c["citations"][0]["reason"] for c in result["claims"][S.CHUNK_ITEMS:2 * S.CHUNK_ITEMS]},
                         {"The model check failed (TimeoutError)."})

    def test_the_summary_a_chat_answer_keeps_has_the_counts_and_seconds_and_no_sentence(self):
        _, result = S.check_and_mark(self.db, self.case.id, f"The tenant holds the keys [p]({self.p2}).",
                                     judge=self.judge("partly"))
        kept = S.summary(result)
        self.assertEqual(kept["counts"][S.PARTLY], 1)
        self.assertEqual(kept["model"]["usage"], {"prompt_tokens": 10, "completion_tokens": 5})
        self.assertIsInstance(kept["seconds"], float)
        self.assertNotIn("keys", json.dumps(kept))

    def test_a_failed_model_call_leaves_the_citation_unchecked_saying_why_and_marks_nothing(self):
        def broken(prompt):
            raise TimeoutError("slow")
        marked, result = S.check_and_mark(self.db, self.case.id, f"The tenant holds the keys [p]({self.p2}).",
                                          judge=broken)
        cite = result["claims"][0]["citations"][0]
        self.assertEqual((cite["state"], cite["reason"]), (S.UNCHECKED, "The model check failed (TimeoutError)."))
        self.assertNotIn(S.MARK, marked)
        self.assertIn("1 could not be checked", marked)

    def test_a_spent_budget_stops_the_model_call(self):
        result = S.check(self.db, self.case.id, f"The tenant holds the keys [p]({self.p2}).",
                         judge=self.judge("supports"), budget=lambda: "This case's AI budget is spent.")
        self.assertEqual(self.calls, [])
        self.assertEqual(result["claims"][0]["citations"][0]["reason"], "This case's AI budget is spent.")

    def test_a_citation_standing_alone_backs_the_sentences_before_it_and_a_missing_page_says_so(self):
        answer = (f"- Travis Kell rents bay 4. He pays $650 a month. [lease, p.2]({self.p2})\n"
                  f"Mateo Ruiz signed [p](doc://{self.file.id}/9).")
        result = S.check(self.db, self.case.id, answer, judge=None)
        texts = [c["text"] for c in result["claims"]]
        self.assertEqual(texts[:2], ["Travis Kell rents bay 4.", "He pays $650 a month."])
        # a name alone is not settled by code: with no model it stays unchecked, saying so
        self.assertEqual([c["state"] for c in result["claims"][:2]], [S.UNCHECKED, S.SUPPORTS])
        self.assertEqual(result["claims"][2]["citations"][0]["reason"], "The document has no page 9.")

    def test_a_payment_is_read_from_its_fields_with_minor_units_as_written(self):
        _, _, rows = self.source(rows=1, amount=65000)
        row = rows[0]
        answer = f"Exact source company was paid 650.00 [payment](txn://{row.id})."
        result = S.check(self.db, self.case.id, answer, judge=None)
        self.assertEqual(result["claims"][0]["citations"][0]["state"], S.SUPPORTS)
        foreign = f"Paid 650.00 [payment](txn://{uuid.uuid4()})."
        self.assertEqual(S.check(self.db, self.case.id, foreign)["claims"][0]["citations"][0]["state"], S.UNCHECKED)

    def test_the_limits_are_named_never_silent(self):
        answer = "\n".join(f"Line {i} names nobody [p]({self.p2})." for i in range(S.MAX_CLAIMS + 2))
        result = S.check(self.db, self.case.id, answer, judge=self.judge("supports"))
        over = [c for c in result["claims"] if "limit of" in (c["citations"][0]["reason"] or "")]
        self.assertGreaterEqual(len(over), 2)
        self.assertEqual(result["citations"], S.MAX_CLAIMS + 2)

    def test_the_check_sections_are_not_read_as_claims(self):
        answer = f"Travis Kell pays $650 a month [p]({self.p2})."
        marked, _ = S.check_and_mark(self.db, self.case.id, answer, judge=self.judge("supports"))
        self.assertEqual(len(S.claims(marked)), 1)
        figures = answer + f"\n\n**Figures to check: not found in the records cited beside them**\n- 999 in \"x\" ([source 1]({self.p2}))."
        self.assertEqual(len(S.claims(figures)), 1)

    def test_switched_off_stores_the_answer_as_written_and_says_it_was_not_checked(self):
        import os
        os.environ[S.SWITCH] = "0"
        try:
            marked, result = S.check_and_mark(self.db, self.case.id, f"x [p]({self.p2}).")
        finally:
            del os.environ[S.SWITCH]
        self.assertEqual(marked, f"x [p]({self.p2}).")
        self.assertFalse(result["available"])


def test_every_stored_answer_goes_through_the_source_check():
    root = Path(__file__).resolve().parents[1]
    chat = (root / "routers" / "chat.py").read_text()
    assert chat.index("supported_answer(") < chat.index("append_conversation_turn(\n")
    # chat keeps the check's counts, model calls and seconds with the answer's cost record
    assert chat.index("supported_answer(") < chat.index('"citation_support": citation_summary(')
    agent = (root / "services" / "agent" / "service.py").read_text()
    assert agent.index("storage.supported_answer(") < agent.index('"citation_support": citation_support')



def test_an_openai_gpt5_call_carries_a_reasoning_effort_and_other_values_are_not_sent():
    from types import SimpleNamespace

    import importlib

    L = importlib.import_module("services.llm_service")

    sent = []

    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    sent.append(kwargs)
                    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
                                           usage=None, model="gpt-5-mini", id="x")
    context = L.LLMExecutionContext("openai", "gpt-5-mini")
    context._client = Client()
    context.call("p", json_mode=True, reasoning_effort="low")
    context.call("p", json_mode=True, reasoning_effort="max")  # a DeepSeek value: not sent to OpenAI
    assert sent[0].get("reasoning_effort") == "low"
    assert "reasoning_effort" not in sent[1]
