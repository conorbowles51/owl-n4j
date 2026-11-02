"""03 section 11.5 and S-6: the chat never invents page 1, and is not told to cite rec:// ids that no passage it is
given carries (phone thread text is not in chat retrieval)."""
from __future__ import annotations

from services.llm_service import LLMExecutionContext


def test_the_chat_prompt_gives_no_page_when_none_is_known_and_promises_no_record_ids():
    ctx = object.__new__(LLMExecutionContext)
    ctx.system_context, ctx.analysis_guidance = "synthetic system", "synthetic guidance"
    sent = {}

    def call(prompt, temperature=0.0):
        sent["prompt"] = prompt
        return "synthetic answer"
    ctx.call = call
    answer, prompt = ctx.answer_question_with_prompt("synthetic question", "--- Passage 1: synthetic.pdf ---\nx")
    assert answer == "synthetic answer" and prompt == sent["prompt"]
    assert "use page 1" not in prompt
    assert "never write p.1 for an unknown page" in prompt
    assert "(doc://document_filename.pdf)" in prompt  # the no-page form
    assert "rec://" not in prompt  # the passage headers carry no record id, so the model would have to invent one
