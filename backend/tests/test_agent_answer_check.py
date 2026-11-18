from services.agent import answer_check as A


def call(name, preview=None, summary="", status="success", args=None):
    return {"name": name, "status": status, "summary": summary, "result_preview": preview, "arguments": args or {}}


def test_empty_searches_send_a_normal_run_back_once_with_what_was_tried():
    trace = [call("search_case", {"total_matching": 0}, args={"query": "launch"}),
             call("get_contact_and_money_between", {"total_matching": 0})]
    state = {}
    msg = A.check_message(trace, state)
    assert msg and "search_case" in msg and "launch" in msg and "read_scope_with_model" in msg
    assert A.check_message(trace, state) is None  # once only


def test_a_run_whose_searches_found_things_is_not_sent_back():
    trace = [call("search_case", {"total_matching": 4}), call("get_timeline", {"events": [1]})]
    assert A.check_message(trace, {}) is None


def test_a_search_that_was_retried_with_another_tool_that_found_something_is_not_sent_back():
    trace = [call("search_case", {"total_matching": 0}), call("read_scope_with_model", {"records_read": 40, "relevant": [1]})]
    assert A.check_message(trace, {}) is None


def test_failed_calls_are_not_counted_as_empty_searches():
    assert A.check_message([call("search_case", None, status="error")], {}) is None


def test_none_found_answer_must_name_what_was_searched():
    trace = [call("search_case", {"total_matching": 0}, args={"query": "x"})]
    assert "what was searched" in A.check_message(trace, {})


# ---- C2e: the question's parts are planned first and each looked for (followups m11180017126956 item 2) -----------

def test_the_question_names_its_parts_and_a_part_never_looked_for_sends_the_run_back_once():
    from services.agent import answer_check as A
    q = "Did Mateo Ruiz call Desmond Okafor or +1 (410) 555-0199 after the $500 payment on 3 May?"
    assert A.question_parts(q) == ["+1 (410) 555-0199", "$500", "Mateo Ruiz", "Desmond Okafor"]
    assert "Mateo Ruiz; Desmond Okafor" in A.plan_message(q)
    trace = [{"name": "phone_messages", "status": "success", "arguments": {"query": "Mateo"}, "result_preview": {"total": 3}},
             {"name": "get_financial_transactions", "status": "success", "arguments": {"min_amount": 500},
              "result_preview": {"total": 1}}]
    state = {}
    msg = A.parts_message(q, trace, state)
    assert "Desmond Okafor" in msg and "+1 (410) 555-0199" in msg and "Mateo Ruiz" not in msg.split("no tool call")[1]
    assert A.parts_message(q, trace, state) is None  # once per run
    trace.append({"name": "search_case", "status": "success", "arguments": {"query": "Okafor 4105550199"}})
    assert A.parts_message(q, trace, {}) is None


def test_a_question_with_no_names_has_no_plan_note():
    from services.agent import answer_check as A
    assert A.question_parts("what happened on the nights of the thefts?") == []
    assert A.plan_message("what happened on the nights of the thefts?") is None
