from services.relations import report as R, rules
from tests.test_relations_engine import Fake, it, members, engine, T0
from datetime import timedelta


def run_view(with_hyp):
    items = dict([it("m", "phone_record", T0, label="Meeting", phone="A"), it("p", "financial_transaction", T0 + timedelta(hours=3),
                                                                           label="Payment <b>", precision="day"),
                  it("far", "financial_transaction", T0 + timedelta(days=300), label="Old payment", precision="day")])
    res = engine.run(Fake(items), members(items))
    hyp = None
    if with_hyp:
        hyp = {"model": "stub-model", "status": "A model reading. No person has confirmed it.", "no_links": "Old payment: nothing found.",
               "items": [{"kind": "coincidence", "statement": "Chance.", "predicts": "", "for": [], "against": [{"cite": "rec://x", "text": "t"}],
                          "distinguishing_record": "third phone", "search": "all phones: none", "accepted": None}]}
    return {"result": res, "hypotheses": hyp}


def test_report_states_search_and_model_reading_and_escapes():
    html = R.render_html(case_name="Case", generated_by="Neil", group={}, run=run_view(True))
    assert "Candidate links" in html and "Pairs with no link found" in html
    assert "Searched:" in html and "not proof that no link exists" in html
    assert "A model reading by stub-model" in html and "Not confirmed by a person." in html
    assert "Payment &lt;b&gt;" in html and "Payment <b>" not in html
    assert "No explanations" in R.render_html(case_name="C", generated_by="N", group={}, run=run_view(False))


def test_report_refuses_a_group_with_no_finished_run():
    import pytest
    with pytest.raises(ValueError):
        R.render_html(case_name="C", generated_by="N", group={}, run={"result": None})


def test_report_renders_a_pdf():
    pdf = R.render_pdf(case_name="Case", generated_by="Neil", group={}, run=run_view(True))
    assert pdf[:4] == b"%PDF"


def test_a_long_report_says_how_many_it_lists_of_how_many():
    run = run_view(False)
    one = run["result"]["candidates"][0] if run["result"]["candidates"] else None
    base = one or {"kind": "time_proximity", "members": [], "key": "time", "strength": "faint", "reasons": ["r"], "chance": {"words": "", "reading": "none"}}
    run["result"]["candidates"] = [base] * (R.REPORT_CANDIDATES + 5)
    html = R.render_html(case_name="C", generated_by="N", group={}, run=run)
    assert f"lists the {R.REPORT_CANDIDATES:,} strongest of {R.REPORT_CANDIDATES + 5:,} candidate links" in html


def test_a_date_only_item_shows_its_date_and_no_time_of_day():
    run = run_view(False)
    run["result"]["items"][1] = {**run["result"]["items"][1], "at": "2026-03-01T00:00:00+00:00", "precision": "day"}
    html = R.render_html(case_name="C", generated_by="N", group={}, run=run)
    assert "2026-03-01</span>" in html and "2026-03-01 00:00" not in html


def _corroborated():
    """A run that asked a Corroborate question: its result holds the grid, the checks and the lanes' sources."""
    from services.corroborate import engine as corroborate
    from services.relations import lanes as L
    from tests.corroborate_world import INCIDENTS, FakeStore
    d = INCIDENTS[0]
    store = FakeStore()
    c = corroborate.run(store, [{"type": "record", "id": f"m1:{d}"}, {"type": "record", "id": f"m2:{d}"}], {"kind": "every_time"})
    run = run_view(False)
    run["result"]["corroboration"] = c
    lanes = [L.build(store, c, i["id"]) for i in c["comparison"]["incident"] + c["comparison"]["ordinary"]]
    return run, c, lanes


def test_report_prints_the_corroborate_result_the_screen_shows():
    """17 Nov 2026: 43 finished runs on live hold a Corroborate result, and their PDF printed only the link analysis."""
    run, c, lanes = _corroborated()
    html = R.render_html(case_name="C", generated_by="N", group={}, run=run, lanes=lanes)
    assert f"Corroborate: {c['level']['name']}" in html and R._e(c["level"]["sentence"]) in html
    assert "What was present, and on which instances" in html and html.count("<tr>") >= len(c["grid"]) + 1
    for row in c["grid"]:
        assert R._e(row["label"]) in html
        assert f"{row['incident']['present']} of {row['incident']['of']}" in html
    for k in c["checks"]:
        assert R._e(R.CHECK_WORDS.get(k["check"], k["check"])) in html
    assert f"Checks made ({len(c['checks']):,})" in html and "Not in this pattern" in html
    for n in c["not_in_pattern"]:
        assert R._e(n["who"]) in html
    for i in c["comparison"]["incident"] + c["comparison"]["ordinary"]:
        assert R._e(i["label"]) in html
    cited = {ref for row in c["grid"] for refs in row["records"].values() for ref in refs}
    assert cited and all(R._e(ref) in html for ref in cited)
    events = [e for s in lanes for lane in s["lanes"] for e in lane["events"]]
    assert "Story lanes" in html and events and all(R._e(e["text"]) in html for e in events)
    assert R.render_pdf(case_name="C", generated_by="N", group={}, run=run, lanes=lanes)[:4] == b"%PDF"


def test_a_run_stopped_after_corroborate_reports_it_and_says_the_link_analysis_did_not_finish():
    """10 failed runs on live keep the Corroborate result alone; their report raised on the missing link counts."""
    run, c, _ = _corroborated()
    run["result"] = {"corroboration": c, "partial": True}
    html = R.render_html(case_name="C", generated_by="N", group={}, run=run)
    assert f"Corroborate: {c['level']['name']}" in html and "link analysis did not finish" in html
    assert "Story lanes" not in html
