"""Live answers that still broke the writing standard after every post-check (lx-agentcost I).

7 days to 10 Nov 2026: 219 of 238 live answers passed services.writing_standard.find_problems; through today's
post-checks, 223. The 15 left: graph link names (TRANSFERRED_TO, READ_FROM, LEGAL_REPRESENTATIVE_OF), "null", codes
inside a longer word ("P3-level"), banned words and phrases ("Notably", "leverage", "successfully"), and evidence file
names ("IMG_00001.jpg") taken for internal terms."""
import unittest

from langchain_core.messages import AIMessage

from services import writing_standard
from services.agent import graph


class _Rewriter:
    def __init__(self, reply):
        self.reply, self.requests = reply, []

    def invoke(self, messages):
        self.requests.append(messages)
        return AIMessage(content=self.reply)


class StandardBreakTests(unittest.TestCase):
    def test_an_evidence_file_name_is_not_an_internal_term(self):
        text = 'Orrin to Alder: "on my way" (attachment IMG_00001.jpg) [message](rec://1b0eeb0a-9c5f)'
        self.assertEqual(writing_standard.find_problems(text), [])
        self.assertIn("IMG_00001.jpg", writing_standard.clean(text))

    def test_a_link_name_or_banned_word_left_in_the_answer_is_rewritten_once(self):
        answer = ("Notably, the graph has 38 TRANSFERRED_TO links between the accounts [statement p.2]"
                  "(doc://f1/2), and the opening equals the closing with null discrepancy.")
        plain = "The graph has 38 payment links between the accounts [statement p.2](doc://f1/2), and no gap."
        model = _Rewriter(plain)
        _, text = graph._in_plain_words(model, AIMessage(content=answer))
        self.assertEqual(text, plain)
        self.assertEqual(len(model.requests), 1)
        request = model.requests[0][0].content
        for word in ("Notably", "TRANSFERRED_TO", "null"):
            self.assertIn(word, request)

    def test_a_rewrite_that_drops_a_citation_keeps_the_original(self):
        answer = "Notably, 3 payments went out [statement p.2](doc://f1/2)."
        _, text = graph._in_plain_words(_Rewriter("Three payments went out."), AIMessage(content=answer))
        self.assertIn("(doc://f1/2)", text)

    def test_a_clean_answer_is_not_rewritten(self):
        model = _Rewriter("unused")
        _, text = graph._in_plain_words(model, AIMessage(content="Three payments went out [p.2](doc://f1/2)."))
        self.assertEqual(model.requests, [])


if __name__ == "__main__":
    unittest.main()
