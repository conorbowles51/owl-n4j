from datetime import datetime, timedelta, timezone

from services.relations import engine, matrix, rules

T0 = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


class Fake:
    def __init__(self, items):
        self.items = items

    def load_items(self, members):
        return [self.items[m["id"]] for m in members]

    def base(self, items):
        return {"period_days": 200, "days_with": {"financial_transaction": 20, "phone_message": 150, "phone_location": 100}}

    def identifier_counts(self, kind, value):
        return {"count": 2, "base": 900, "unit": "ledger rows"}

    def place_stats(self, lat, lon, r):
        return {"phones_near": 1, "phones_total": 5, "days_at_place": {}, "days_active": {}}

    def events(self, phones):
        return []

    def streams(self, phones):
        return {p: [] for p in phones}

    def together_apart(self, a, b):
        return {"days": 0}


def it(id_, type_, at=None, **kw):
    return id_, {"ref": f"{type_}:{id_}", "type": type_, "id": id_, "label": kw.pop("label", id_),
                 "at": at.isoformat() if at else None, "identifiers": [], "names": [], **kw}


def members(items):
    return [{"type": v["type"], "id": k} for k, v in items.items()]


def test_planted_links_and_non_links():
    items = dict([
        it("msg", "phone_record", T0, label="message", time_kind="phone_message", phone="A"),
        it("meet", "phone_record", T0 + timedelta(hours=20), label="meeting", phone="B"),
        it("pay", "financial_transaction", T0 + timedelta(days=1, hours=20), label="payment", precision="day", time_kind="financial_transaction",
           names=["HARBOR TRADING LLC"]),
        it("doc", "evidence", label="contract", identifiers=rules.extract_identifiers("Harbor Trading LLC agreed")),
        it("far", "financial_transaction", T0 + timedelta(days=150), label="old payment", precision="day", names=["Acme"]),
    ])
    res = engine.run(Fake(items), members(items))
    kinds = {(c["kind"], tuple(sorted(c["members"]))) for c in res["candidates"]}
    assert ("shared_identifier", ("evidence:doc", "financial_transaction:pay")) in kinds
    assert any(c["kind"] == "sequence" for c in res["candidates"])
    nl = {tuple(sorted(n["members"])): n for n in res["no_links"]}
    pair = nl[("financial_transaction:far", "financial_transaction:pay")]
    assert pair["searched"] and "not proof" in pair["says"]
    # a document and a place-less meeting: only identifiers reach them; nothing found reports its search
    assert nl[("evidence:doc", "phone_record:meet")]["analyses"] == ["shared_identifier"]
    assert res["counts"]["pairs"] == 10 and res["analyses"]


def test_types_no_analysis_reaches_say_so():
    items = dict([it("pl", "place", label="Pier", place={"lat": 1, "lon": 1, "radius_m": 50, "source": "map"}),
                  it("acct", "financial_account", label="Account")])
    res = engine.run(Fake(items), members(items))
    assert res["no_links"][0]["says"].startswith("No analysis links")


def test_matrix_has_every_pair():
    assert len(matrix.table()) == 45
    empty = {frozenset(c) for c in matrix.empty_cells()}
    assert frozenset(("place", "financial_account")) in empty
    assert frozenset(("phone_record", "financial_transaction")) not in empty
