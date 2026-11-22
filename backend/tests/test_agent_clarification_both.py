"""A clarification that offers "both" as an answer is not asked: the agent answers every reading (probe 22 Nov,
P4 step 2: "What comes before each of those checks?" after an answer about Penn's five checks got only "do you want
the ledger side or the conversation side?", with a third option "Both, for each check"). Of the 71 live
clarifications on 22 Nov, that was the only one whose option label began with Both or All of the above."""
from __future__ import annotations

from services.agent.tools import AgentToolContext, make_agent_tools


def _ask(options):
    tools = {t.name: t for t in make_agent_tools(AgentToolContext(case_id="case-1"))}
    return tools["request_clarification"].invoke({"question": "Which side?", "options": options})


def test_an_option_to_have_both_readings_means_answer_both_not_ask():
    out = _ask([{"id": "ledger_before", "label": "Transaction before each check"},
                {"id": "conversation_before", "label": "Messages and calls before each payment"},
                {"id": "both", "label": "Both, for each check"}])
    assert "clarification" not in out
    assert out["status"] == "error"
    assert "answer every reading now" in out["summary"] and "Both, for each check" in out["summary"]


def test_a_real_choice_is_still_asked_even_when_an_id_says_both():
    # live 28 Aug and 27 May: "both" ids that are choices, not "every reading"
    for options in ([{"id": "one", "label": "Treat them as one witness"},
                     {"id": "both", "label": "Treat them as two separate witnesses"}],
                    [{"id": "either", "label": "Companies linked to either"},
                     {"id": "both", "label": "Companies directly linked to both (intersection)"}],
                    [{"id": "top", "label": "The 50 most mentioned people"},
                     {"id": "all", "label": "All persons (export full list of ~1,300 people)"}]):
        out = _ask(options)
        assert out["status"] == "success" and len(out["clarification"]["options"]) == 2
