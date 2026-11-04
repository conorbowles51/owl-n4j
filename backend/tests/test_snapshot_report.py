"""Snapshot save and report (BUG-009, BUG-012, FEAT-008)."""
import io
import types

import pytest

from services import snapshot_report as sr


def _snapshot(**over):
    snap = {
        "id": "snapshot_x",
        "name": "Payments to Acme",
        "notes": "Working view for the March interview.",
        "created_at": "2026-11-04T08:00:00",
        "subgraph": {
            "nodes": [
                {"key": "p1", "label": "Jane Roe", "type": "Person", "x": -50, "y": 10, "color": "#3366cc",
                 "properties": {"source_files": ["bank-march.pdf"]}},
                {"key": "e1", "label": "Wire 7,540", "type": "Transaction", "x": 80, "y": -40},
            ],
            "links": [{"source": "p1", "target": "e1", "type": "SENT"}],
        },
        "timeline": [
            {"key": "e1", "name": "Wire 7,540", "type": "Transaction", "date": "2022-11-30",
             "source_references": ["bank-march.pdf p.4"], "connections": []},
        ],
    }
    snap.update(over)
    return snap


def test_privilege_marking_reuses_the_ledger_values():
    assert sr.privilege_label("unmarked") == "No privilege marking selected"
    assert sr.privilege_label("confidential") == "Confidential"
    assert sr.privilege_label("privileged_confidential") == "Privileged and confidential"
    with pytest.raises(sr.SnapshotReportError):
        sr.privilege_label("attorney_eyes_only")


def test_report_prints_only_the_snapshots_own_events_with_sources_and_marking():
    html = sr.render_snapshot_report_html(
        _snapshot(), case_name="Case A", generated_by="Jobs", privilege_marking="privileged_confidential"
    )
    assert "Wire 7,540" in html
    assert "Source Appendix" in html and "bank-march.pdf p.4" in html
    assert "bank-march.pdf" in html  # the entity's own source
    assert html.count("Privileged and confidential") >= 2  # cover banner and page footer
    assert sr.PRIVILEGE_BASIS in html
    assert "Snapshot report" in html
    assert "Events:</strong> 1" in html
    assert "<svg class=\"graph-svg\"" in html


def test_report_never_reaches_beyond_the_snapshot():
    # An event that is not in the snapshot's stored timeline is never printed, whatever the case holds.
    html = sr.render_snapshot_report_html(_snapshot(timeline=[]), case_name="Case A", generated_by="Jobs")
    assert "Wire 7,540" in html  # still drawn as an entity
    assert "None of the entities in this snapshot is a dated event." in html
    assert "Source Appendix" not in html


def test_graph_is_vector_from_saved_positions():
    svg = sr.graph_svg(_snapshot()["subgraph"])
    assert svg.startswith("<svg") and "<line" in svg and svg.count("<circle") == 2
    positions, all_saved = sr.layout_positions(_snapshot()["subgraph"]["nodes"])
    assert all_saved
    xs = [p[0] for p in positions.values()]
    assert min(xs) >= 0 and max(xs) <= sr.GRAPH_WIDTH


def test_oversized_snapshot_is_refused_not_clipped():
    nodes = [{"key": f"n{i}", "label": str(i)} for i in range(sr.MAX_REPORT_NODES + 1)]
    with pytest.raises(sr.SnapshotReportError, match="No partial report"):
        sr.render_snapshot_report_html(_snapshot(subgraph={"nodes": nodes, "links": []}), case_name="", generated_by="")


def test_pdf_renders_with_marking_on_every_page():
    pytest.importorskip("weasyprint")
    pypdf = pytest.importorskip("pypdf")
    pdf = sr.render_snapshot_report_pdf(_snapshot(), case_name="Case A", generated_by="Jobs",
                                        privilege_marking="confidential")
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    text = [page.extract_text() for page in reader.pages]
    assert all("Confidential" in t for t in text)
    assert any("Wire 7,540" in t for t in text)


def test_saving_from_the_graph_keeps_only_the_events_among_its_entities(monkeypatch):
    from routers import snapshots as router

    asked = {}

    def fake_fetch(db, case_id, keys, require_all=True):
        asked["keys"] = list(keys)
        asked["require_all"] = require_all
        return [{"key": "e1", "name": "Wire", "date": "2022-11-30"}]

    import services.timeline_view_service as tvs
    monkeypatch.setattr(tvs, "_fetch_current_events", fake_fetch)
    stored = {}
    monkeypatch.setattr(router.snapshot_storage, "save", lambda sid, data, **k: stored.update({sid: data}))
    monkeypatch.setattr(router.snapshot_storage, "get", lambda sid, **k: stored.get(sid))
    case = types.SimpleNamespace(id="11111111-1111-1111-1111-111111111111", title="Case A")
    monkeypatch.setattr(router, "_case_for", lambda db, case_id, user: case)
    body = router.SnapshotCreate(
        name="s", notes="", case_id=case.id,
        subgraph={"nodes": [{"key": "p1"}, {"key": "e1"}, {"key": "p1"}], "links": [{"source": "p1", "target": "e1"}]},
    )
    out = router.create_snapshot(body, user={"username": "u"}, db=None, db_user=None)
    assert asked == {"keys": ["p1", "e1"], "require_all": False}
    assert out.timeline_count == 1 and out.node_count == 3 and out.link_count == 1
    saved = next(iter(stored.values()))
    assert saved["timeline"] == [{"key": "e1", "name": "Wire", "date": "2022-11-30"}]
    assert saved["case_name"] == "Case A"


def test_snapshot_saves_even_when_events_cannot_be_read(monkeypatch):
    from routers import snapshots as router
    import services.timeline_view_service as tvs

    def broken(*a, **k):
        raise RuntimeError("graph store unreachable")

    monkeypatch.setattr(tvs, "_fetch_current_events", broken)
    stored = {}
    monkeypatch.setattr(router.snapshot_storage, "save", lambda sid, data, **k: stored.update({sid: data}))
    monkeypatch.setattr(router.snapshot_storage, "get", lambda sid, **k: stored.get(sid))
    case = types.SimpleNamespace(id="11111111-1111-1111-1111-111111111111", title="Case A")
    monkeypatch.setattr(router, "_case_for", lambda db, case_id, user: case)
    body = router.SnapshotCreate(name="s", notes="", case_id=case.id, subgraph={"nodes": [{"key": "p1"}], "links": []})
    out = router.create_snapshot(body, user={"username": "u"}, db=None, db_user=None)
    assert out.node_count == 1 and out.timeline_count == 0 and len(stored) == 1
