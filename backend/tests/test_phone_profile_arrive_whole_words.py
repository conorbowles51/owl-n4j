"""'Did it arrive whole' lines are words, never a raw object (followups m110416530724934: live phones printed
'rows: the report states nothing, [object Object] read' and 'ws_only_texts: the report states 18, 0 read' under
'Every part of the report matches its own counts')."""
from services.phone.profile import profile_sections, stated_vs_read_words

LIVE_ROWS = {"stored": {"f": 4, "r": 637, "x": 0}, "consumed": {"f": 4, "r": 637, "x": 0}}


def test_rows_tally_is_words_with_each_kind():
    w = stated_vs_read_words("rows", None, LIVE_ROWS)
    assert w == ("Rows Loupe stored from this document: 637 records, 4 files, 0 extra-information entries; "
                 "every one is reached again from the report.")
    assert "object" not in w.lower() and "{" not in w


def test_rows_not_all_reached_names_what_was_reached():
    w = stated_vs_read_words("rows", None, {"stored": {"r": 1200, "f": 1, "x": 3}, "consumed": {"r": 1190, "f": 1}})
    assert w.endswith("reached again from the report: 1,190 records, 1 file, 0 extra-information entries.")


def test_layout_whitespace_is_explained_not_shown_as_a_loss():
    w = stated_vs_read_words("ws_only_texts", 18, 0)
    assert w == ("Whitespace-only text: the report has 18, Loupe kept 0; the other 18 are layout between elements, "
                 "kept as nothing by design.")


def test_a_plain_count_difference_keeps_both_numbers():
    assert stated_vs_read_words("elements", 1451062, 1451061) == \
        "Elements: the report states 1,451,062, Loupe read 1,451,061."
    assert stated_vs_read_words("files", 9, 7) == "Files: the report states 9, Loupe read 7."
    assert stated_vs_read_words("comments", None, 2) == "Comments: the report states nothing, Loupe read 2."


def test_the_export_section_uses_the_words():
    p = {"verdict": {"sentence": "Read in full."}, "needs": [], "months": [], "busiest_weeks": [], "top_people": [],
         "apps": [], "owner": {"label": None, "words": "not set"},
         "report": {"filename": "Report.xml", "form": "full", "report_version": "7.48", "producer": None,
                    "extraction_type": None, "container_sha256": None},
         "selection": [], "files": {"total": 0, "by_category": {}, "verification": {}},
         "deleted": {"comm_events": 0, "by_type": []}, "coverage": [], "data_periods": [],
         "completeness": {"reconciliation": "exact", "held": [], "documents": [
             {"document_index": 0, "stated_vs_read": [{"what": "rows", "stated": None, "read": LIVE_ROWS},
                                                      {"what": "ws_only_texts", "stated": 18, "read": 0}]}]}}
    whole = dict(profile_sections(p))["Did it arrive whole"]
    assert whole == ["Every part of the report matches its own counts.",
                     stated_vs_read_words("rows", None, LIVE_ROWS), stated_vs_read_words("ws_only_texts", 18, 0)]
    assert not any("{" in line or "'stored'" in line for line in whole)
