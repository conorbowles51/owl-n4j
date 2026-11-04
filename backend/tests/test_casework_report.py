"""Casework report: findings first with linked evidence, sections in the chosen order (FEAT-003, FEAT-009)."""
import io

import pytest

from services import casework_report as cr


def _entries():
    return {
        "findings": [
            {"title": "Low one", "significance": "low", "body": "minor", "links": []},
            {"title": "Key payment", "significance": "high", "lifecycle_state": "active", "body": "7,540 to third parties",
             "author_name": "A. Investigator",
             "links": [{"relationship": "supports", "target_type": "evidence", "target_label": "BBVA Nov 2022.pdf"}]},
            {"title": "Withdrawn deleted", "significance": "high", "deleted_at": "2026-11-01", "links": []},
        ],
        "theories": [{"title": "Layering", "lifecycle_state": "investigating", "body": "t", "links": []}],
        "notes": [{"title": None, "body": "call back Tuesday", "links": []}],
    }


def test_findings_lead_and_carry_their_linked_evidence():
    html = cr.render_casework_report_html(_entries(), sections=["findings", "theories", "notes"], case_name="Case A",
                                          generated_by="Jobs")
    assert html.index("Findings (2)") < html.index("Theories (1)") < html.index("Notes (1)")
    assert html.index("Key payment") < html.index("Low one")  # high significance first
    assert "Supports</strong> · Evidence file: BBVA Nov 2022.pdf" in html
    assert "Withdrawn deleted" not in html  # deleted entries never print
    assert "Untitled note" in html


def test_sections_follow_the_chosen_order_and_can_be_left_out():
    html = cr.render_casework_report_html(_entries(), sections=["notes", "findings"], case_name="", generated_by="")
    assert html.index("Notes (1)") < html.index("Findings (2)")
    assert "Theories (" not in html
    with pytest.raises(cr.CaseworkReportError):
        cr.normalise_sections(["audit_log"])
    with pytest.raises(cr.CaseworkReportError):
        cr.normalise_sections([])


def test_no_audit_log_or_timeline_and_marking_on_cover_and_footer():
    html = cr.render_casework_report_html(_entries(), sections=["findings"], case_name="", generated_by="",
                                          privilege_marking="privileged_confidential")
    assert "audit" not in html.lower() and "timeline" not in html.lower()
    assert html.count("Privileged and confidential") >= 2


def test_collect_entries_reads_every_page():
    pages = {0: {"entries": [{"i": n} for n in range(200)], "total": 250}, 200: {"entries": [{"i": n} for n in range(50)], "total": 250}}
    calls = []
    out = cr.collect_entries(lambda t, limit, offset: calls.append(offset) or pages[offset], "finding")
    assert len(out) == 250 and calls == [0, 200]


def test_pdf_renders():
    pytest.importorskip("weasyprint")
    pypdf = pytest.importorskip("pypdf")
    pdf = cr.render_casework_report_pdf(_entries(), sections=["findings"], case_name="Case A", generated_by="Jobs",
                                        privilege_marking="confidential")
    text = "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
    assert "Key payment" in text and "Confidential" in text
