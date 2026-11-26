"""Corroborate's people name a phone's owner as the phones screens do (followups, 26 Nov).

Fails on the code before: a phone owner known by no dossier was 'the user of Phone 1 (+17175550211)' with no name, so
Corroborate and Mentions named Priya Halloran differently from the phones workspace and Conversations, and 'Priya
Halloran' in a text matched nobody (Demo 2, live, 26 Nov)."""
from types import SimpleNamespace

from services.corroborate import store as S

E1, E2, E3 = "e1000000-0000-0000-0000-000000000001", "e2000000-0000-0000-0000-000000000002", \
    "e3000000-0000-0000-0000-000000000003"


def _store(monkeypatch, *, dossiers=(), owners=(), names=None, accounts=()):
    st = S.CaseStore.__new__(S.CaseStore)
    st.case, st.c, st._people, st.db = "case", {"c": "case"}, None, SimpleNamespace(connection=lambda: None)

    def q(sql, *a, **k):
        if "FROM case_profiles" in sql:
            return list(dossiers)
        if "FROM phone_participations" in sql:
            return list(owners)
        if "FROM financial_accounts" in sql:
            return list(accounts)
        raise AssertionError(sql)
    st.q = q
    import services.phone.readings as readings
    import services.phone.labels as labels
    monkeypatch.setattr(readings, "phone_labels", lambda conn, case: {E1: "Phone 1", E2: "Phone 2", E3: "Phone 3"})

    class Ctx:
        def __init__(self, conn, case):
            pass

        def label(self, ext, is_phone_owner=None, **k):
            return {"name": (names or {}).get(ext)}
    monkeypatch.setattr(labels, "LabelContext", Ctx)
    return st


def test_a_phone_owner_known_by_no_dossier_carries_the_mapped_name_said_to_be_unconfirmed(monkeypatch):
    st = _store(monkeypatch, owners=[(E1, "+17175550211")], names={E1: "Priya Halloran"},
                accounts=[("a1", "PRIYA HALLORAN", "Bank", "x1234")])
    (p,) = st.people()
    assert p["label"] == "Priya Halloran (not yet confirmed)"
    assert p["names"] == ["Priya Halloran"] and p["name_origin"] == "mapped by the system, not yet confirmed"
    assert p["accounts"] == ["a1"] and p["owner_of"] == "Phone 1, +17175550211"
    from services.corroborate import questions
    (choice,) = questions.people_choices(st)
    assert choice["label"] == "Priya Halloran (not yet confirmed)"
    assert choice["name_origin"] == "mapped by the system, not yet confirmed" and choice["owner_of"] == "Phone 1, +17175550211"
    assert S.M.person_for_name(st.people(), "Priya Halloran was at the lake") == p["key"]


def test_a_name_a_dossier_holds_stays_the_dossiers_and_its_account_is_not_shared(monkeypatch):
    st = _store(monkeypatch, dossiers=[("d1", "Marisol Teague", [])],
                owners=[(E2, "+17175550231")], names={E2: "Marisol Teague"},
                accounts=[("a2", "Marisol Teague", "Bank", "x9")])
    people = {p["key"]: p for p in st.people()}
    phone = people["phone:%s" % E2]
    assert phone["names"] == [] and phone["label"] == "the user of Phone 2 (+17175550231)"
    assert people["person:d1"]["accounts"] == ["a2"]


def test_phones_that_name_one_owner_differently_show_both_names_and_choose_none(monkeypatch):
    st = _store(monkeypatch, owners=[(E1, "+12015550102"), (E3, "+12015550102")],
                names={E1: "Zeno Oakhurst", E3: "Tamsin C."})
    (p,) = st.people()
    assert p["names"] == ["Zeno Oakhurst", "Tamsin C."]
    assert p["label"] == ("the user of Phone 1, +12015550102 (named Zeno Oakhurst or Tamsin C. on its phones, not yet "
                          "confirmed)")


def test_a_phone_with_no_owner_name_keeps_its_number_label(monkeypatch):
    st = _store(monkeypatch, owners=[(E3, "+14435550131")])
    (p,) = st.people()
    assert p["label"] == "the user of Phone 3 (+14435550131)" and p["names"] == [] and "name_origin" not in p
