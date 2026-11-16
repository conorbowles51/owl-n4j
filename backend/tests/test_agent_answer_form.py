"""lx-agentquick A: the one-to-three-sentence rule applies to fact questions only (audit cause 4)."""
import unittest

from services.agent import graph, question_scope as QS

FACT = ["Whose phone was it with Kell on 8 June?", "Who owns the number ending 4411?",
        "How much did Erica Hopper pay on 3 March 2021?", "Did Mateo call Kell after midnight?",
        "What is the balance of account 1234?"]
FULL = ["Give me a detailed report about the phones in this case, include a summary of who owns each phone and "
        "flag any suspicious communications",
        "Analyse the money going out of the Hopper accounts in 2021",
        "Go through the financials for the whole case and tell me what matters",
        "Investigate how Kell and Mateo relate to the tow truck company",
        "Give me an overview of every person in the case and what each did on the night of the theft"]


class AnswerForm(unittest.TestCase):
    def test_fact_questions_keep_the_short_rule(self):
        for q in FACT:
            self.assertEqual(QS.question_kind(q), "fact", q)
            block = QS.block(QS.build(q), question=q)
            self.assertIn(QS.STAY_ON_THE_QUESTION, block, q)
            self.assertNotIn(QS.FULL_ANSWER, block, q)

    def test_analysis_broad_and_report_questions_get_a_full_answer(self):
        for q in FULL:
            self.assertEqual(QS.question_kind(q), "full", q)
            for planning in (False, True):
                block = QS.block(QS.build(q), planning=planning, question=q)
                self.assertIn(QS.FULL_ANSWER, block, q)
                self.assertNotIn("one to three sentences", block, q)
                self.assertNotIn("Leave out accounts", block, q)

    def test_focus_for_uses_the_kind(self):
        class S:  # no database: the accounts read fails and gives none
            def begin_nested(self):
                raise RuntimeError("no db")
        planning, final = QS.focus_for(S(), "c", FULL[0])
        self.assertIn(QS.FULL_ANSWER, final)
        self.assertIn(QS.FULL_ANSWER, planning)
        planning, final = QS.focus_for(S(), "c", FACT[0])
        self.assertIn(QS.STAY_ON_THE_QUESTION, final)

    def test_no_prompt_forces_brevity_on_every_answer(self):
        self.assertNotIn("Be concise", graph._FINAL_ANSWER_SYSTEM_PROMPT)
        import inspect
        self.assertNotIn("professional, concise", inspect.getsource(graph))



class SearchStrategyPrompt(unittest.TestCase):
    """lx-agentquick H: the prompt teaches several phrasings and whole reads, and no longer forbids another search."""

    def test_the_prompt_teaches_search_strategy_and_does_not_forbid_a_second_search(self):
        import inspect
        source = inspect.getsource(graph)
        self.assertIn("Search strategy", source)
        self.assertIn("at least three different ways", source)
        self.assertIn("read whole", source)
        self.assertNotIn("never look for it another way", source)


if __name__ == "__main__":
    unittest.main()
