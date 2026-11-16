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
