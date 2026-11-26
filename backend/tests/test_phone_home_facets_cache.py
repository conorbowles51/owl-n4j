"""The Phones page's counts are read again only when the list they open could differ (followups, 26 Nov).

Fails on the code before: every visit counted every record again (Phone reference 1, live 26 Nov: What 19 s, Who
24-54 s, State 16 s per visit; kept, 15-57 ms)."""
from types import SimpleNamespace

from services.phone import phone_home as H
from services.phone.timeline_lens import TimelineLensFilter

CASE = "11111111-2222-3333-4444-555555555555"


def _f(**kw):
    return TimelineLensFilter.model_validate({"case_id": CASE, **kw})


def test_an_answer_is_counted_once_while_its_key_holds_and_again_when_it_changes(monkeypatch):
    monkeypatch.setattr(H, "_CACHE", {})
    keys, runs = ["k1"], []
    monkeypatch.setattr(H, "answer_key", lambda conn, f, part: keys[0] + "|" + str(part))
    monkeypatch.setattr(H, "_facets", lambda conn, f, part: runs.append(part) or {"kinds": [{"count": len(runs)}]})
    a = H.facets(None, _f(), "kinds")
    a["kinds"][0]["count"] = 99  # a caller changing its answer never changes the kept one
    b = H.facets(None, _f(), "kinds")
    assert runs == ["kinds"] and b == {"kinds": [{"count": 1}]}
    keys[0] = "k2"  # a phone read again, a decision, a zone change: a new key
    assert H.facets(None, _f(), "kinds") == {"kinds": [{"count": 2}]} and runs == ["kinds", "kinds"]


def test_the_key_is_the_lists_snapshot_and_the_who_key_also_holds_the_name_sources(monkeypatch):
    from services.phone import filters
    seen = []
    monkeypatch.setattr(filters, "snapshot", lambda conn, f, extra="": seen.append(extra) or "s:" + extra)
    reads = []

    class Conn:
        def execute(self, sql, params):
            reads.append(str(sql))
            return SimpleNamespace(one=lambda: (len(reads), "t"))
    H.answer_key(Conn(), _f(), "kinds")
    assert reads == [] and seen[-1].startswith("facets|kinds|")
    H.answer_key(Conn(), _f(), "people")
    assert any("case_profiles" in r for r in reads) and any("phone_identities" in r for r in reads)
    assert "facets|people|" in seen[-1] and seen[-1] != "facets|people|"


def test_the_kept_answers_are_bounded(monkeypatch):
    monkeypatch.setattr(H, "_CACHE", {})
    n = iter(range(1000))
    monkeypatch.setattr(H, "answer_key", lambda conn, f, part: "k%d" % next(n))
    monkeypatch.setattr(H, "_facets", lambda conn, f, part: {})
    for _ in range(H._CACHE_LIMIT + 10):
        H.facets(None, _f(), "kinds")
    assert len(H._CACHE) == H._CACHE_LIMIT
