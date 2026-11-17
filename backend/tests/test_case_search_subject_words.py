"""A word looked up on its own is searched for, and two notes with the same words stay two records (lx-sharedsearch;
fail on the code before: "phone" and "between" alone gave no terms, so the shared search found none of the notes
that say them; a theory repeated word for word was merged into its twin and not listed)."""
from services.case_search import service
from services.phone import chat_retrieval as C


def test_one_or_two_common_words_alone_are_searched_for():
    assert C.terms("phone") == ["phone"]
    assert C.terms("Between") == ["between"]
    assert set(C.terms("messages phone")) == {"messages", "phone"}


def test_common_words_still_drop_out_beside_a_subject_or_in_a_longer_question():
    assert C.terms("find the messages about the storage unit") == ["storage", "unit"]
    assert C.terms("who was it that did it") == []


def test_two_casework_entries_with_the_same_words_are_both_kept():
    def cand(i):
        return {"area": "casework", "key": i, "cite": "/cases/c/workspace?view=casework&entry=%s" % i,
                "text": "Theory: Arrendo paid no tax.", "sources": ["words"]}
    kept, removed = service.dedupe([cand("a"), cand("b")])
    assert [h["key"] for h in kept] == ["a", "b"] and removed == 0


def test_the_same_phone_message_on_two_phones_is_still_one_record():
    def cand(i):
        return {"area": "phone_text", "key": i, "cite": "", "text": "meet me at the unit", "sources": ["words"]}
    kept, removed = service.dedupe([cand("a"), cand("b")])
    assert len(kept) == 1 and removed == 1
