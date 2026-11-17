"""A question made only of chat wrapper words searches for them (lx-sharedsearch; fails on the code before:
"phone" alone gave no terms, so the shared search found none of the notes that say "phone")."""
from services.phone import chat_retrieval as C


def test_a_question_of_wrapper_words_alone_searches_for_them():
    assert C.terms("phone") == ["phone"]
    assert set(C.terms("messages phone")) == {"messages", "phone"}


def test_wrapper_words_still_drop_out_beside_a_subject():
    assert C.terms("find the messages about the storage unit") == ["storage", "unit"]


def test_common_grammar_words_alone_still_give_no_terms():
    assert C.terms("who is it") == []
