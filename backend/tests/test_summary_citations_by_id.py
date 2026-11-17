"""scripts/summary_citations_by_id.py: a summary's page links by file name become links by evidence file id."""
import json

from scripts.summary_citations_by_id import entity_file_ids, rewrite

A, B, C = ("e941f20d-3001-40f4-a7db-deb6c6ad4d51", "d00b2c39-f424-490e-8c86-8b01ab79a473",
           "11111111-2222-4333-8444-555555555555")


def test_a_name_the_case_holds_twice_takes_the_id_the_entity_cites():
    facts = json.dumps([{"text": "x", "source_location": {"source_document_id": A, "source_file": "kell.pdf"}}])
    own = entity_file_ids(facts, "[]")
    new, counts = rewrite("Paid ([kell.pdf, p.3](doc://kell.pdf/3)).", own, {"kell.pdf": [A, B]}, {A, B})
    assert new == f"Paid ([kell.pdf, p.3](doc://{A}/3))."
    assert counts == {"by_entity_source": 1}


def test_the_only_file_of_a_name_is_used_and_the_label_stays():
    new, counts = rewrite("([a b.pdf, p.1](doc://a%20b.pdf/1)) and [c.pdf](doc://c.pdf)", {},
                          {"a b.pdf": [C], "c.pdf": [A]}, {A, C})
    assert new == f"([a b.pdf, p.1](doc://{C}/1)) and [c.pdf](doc://{A})"
    assert counts == {"by_only_file": 2}


def test_a_link_that_cannot_be_settled_stays_as_written_and_is_counted():
    locations = json.dumps([{"source_document_id": "gone.pdf", "source_file": "gone.pdf"}])
    text = f"[x.pdf, p.2](doc://x.pdf/2) [gone.pdf, p.1](doc://gone.pdf/1) [y](doc://{B}/4)"
    new, counts = rewrite(text, entity_file_ids("[]", locations), {"x.pdf": [A, B]}, {A, B})
    assert new == text
    assert counts == {"left_ambiguous": 1, "left_no_file": 1, "already_by_id": 1}


def test_an_id_of_a_file_no_longer_in_the_case_is_not_used():
    facts = [{"source_location": {"source_document_id": C, "source_file": "k.pdf"}}]
    new, counts = rewrite("[k.pdf, p.1](doc://k.pdf/1)", entity_file_ids(facts, None), {"k.pdf": [A, B]}, {A, B})
    assert counts == {"left_ambiguous": 1}
