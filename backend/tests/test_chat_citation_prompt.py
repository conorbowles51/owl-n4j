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
    assert "[document name](<Cite>)" in prompt  # the no-page form
    assert "Never build a doc:// link yourself" in prompt  # the passage's Cite carries the evidence file id
    assert "rec://" not in prompt  # the passage headers carry no record id, so the model would have to invent one


def test_the_chat_prompt_says_a_shared_name_is_not_an_identity_link():
    """lx-retrieval 15 Nov, demo case F27/Q8: chat called the phone contact 'Mateo 🔧' (+1 443-555-0181) Mateo Ruiz,
    whose own number is +1 443-555-0112, 4 runs of 4: the context held both numbers, and nothing linked them."""
    ctx = object.__new__(LLMExecutionContext)
    ctx.system_context, ctx.analysis_guidance = "synthetic system", "synthetic guidance"
    ctx.call = lambda prompt, temperature=0.0: "synthetic answer"
    _, prompt = ctx.answer_question_with_prompt("Is the contact Mateo the same person as Mateo Ruiz?", "x")
    assert "SAME PERSON: a shared name is not a link" in prompt
    assert "only when the context links them" in prompt


def test_the_chat_prompt_makes_the_phone_contact_count_the_answer():
    """lx-agentquick, 17 Nov: with the count of 0 calls and messages between Mateo Ruiz's and Desmond Okafor's numbers in
    the context, chat still opened 'Yes' in 2 of 3 live runs from the contact saved as 'Mateo' at another number."""
    ctx = object.__new__(LLMExecutionContext)
    ctx.system_context, ctx.analysis_guidance = "synthetic system", "synthetic guidance"
    ctx.call = lambda prompt, temperature=0.0: "synthetic answer"
    _, prompt = ctx.answer_question_with_prompt("Did Mateo Ruiz ever call or message Desmond Okafor?", "x")
    assert 'CONTACT COUNT: a passage headed "Phone contact between X and Y"' in prompt
    assert 'open with "No"' in prompt
    assert "rec://" not in prompt
