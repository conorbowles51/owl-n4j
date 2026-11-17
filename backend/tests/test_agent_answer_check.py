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
