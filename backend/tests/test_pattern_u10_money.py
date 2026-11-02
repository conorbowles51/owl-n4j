"""04-U10 (cb-pol item I): the money lane and places a person attaches to a payment.

Synthetic ledger rows only. Opt-in PostgreSQL through ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.financial.decisions import Actor
from services.pattern_of_life import money
from tests.phone_pg import fresh_engine, make_case, needs_template

ACTOR = Actor(name="Test Person", email="t@x.test")


def ledger(conn, case):
    """A run, an evidence file, a document and an account, written past the services (synthetic)."""
    ids = {k: uuid.uuid4() for k in ("run", "file", "doc", "acct")}
    uid = conn.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar_one()
    conn.execute(text("INSERT INTO financial_ingestion_runs (id, case_id, status, code_version, ruleset_version, "
                      "started_by_user_id, started_by_email, created_at, updated_at) VALUES (:i, :c, 'completed', "
                      "'t', 't', :u, 't@x.test', now(), now())"), {"i": ids["run"], "c": case, "u": uid})
    conn.execute(text("INSERT INTO evidence_files (id, case_id, original_filename, stored_path, sha256) "
                      "VALUES (:i, :c, 'synthetic.pdf', '/nowhere/synthetic.pdf', :h)"),
                 {"i": ids["file"], "c": case, "h": "a" * 64})
    conn.execute(text("INSERT INTO financial_source_documents (id, case_id, evidence_file_id, ingestion_run_id, "
                      "sha256_at_ingestion, document_type, proof_class, extraction_layer, parser_name, parser_version, "
                      "created_at, updated_at) VALUES (:i, :c, :f, :r, :h, 'bank_statement', 'p2', 2, 't', '1', "
                      "now(), now())"), {"i": ids["doc"], "c": case, "f": ids["file"], "r": ids["run"], "h": "a" * 64})
    conn.execute(text("INSERT INTO financial_accounts (id, case_id, identity_key, currency, created_at, updated_at) "
                      "VALUES (:i, :c, 'synthetic-1', 'USD', now(), now())"), {"i": ids["acct"], "c": case})
    return ids


def txn(conn, case, ids, row, *, tdate=None, pdate=None, odate=None, osrc=None, status="admitted", amount=1000):
    tid = uuid.uuid4()
    odate = odate or tdate or pdate
    osrc = osrc or ("transaction" if tdate else "posted")
    conn.execute(text(
        "INSERT INTO financial_transactions (id, case_id, account_id, source_document_id, ingestion_run_id, ref_id, "
        "row_index, amount_minor, currency, direction, transaction_date, posted_date, value_date, ordering_date, "
        "ordering_date_source, proof_class, extraction_layer, ledger_status, quarantine_reason, content_hash, provenance, metadata, "
        "created_at, updated_at) VALUES (:i, :c, :a, :d, :r, :ref, :n, :amt, 'USD', 'debit', :td, :pd, :vd, :od, :os, 'p2', "
        "2, :st, :qr, :h, '{}', '{}', now(), now())"),
        {"i": tid, "c": case, "a": ids["acct"], "d": ids["doc"], "r": ids["run"], "ref": "T-%d" % row, "n": row,
         "amt": amount, "td": tdate, "pd": pdate, "vd": odate if osrc == "value" else None, "od": odate, "os": osrc, "st": status, "qr": "unreadable_row" if status == "quarantined" else None, "h": uuid.uuid4().hex})
    return tid


def supersede(conn, old, new):
    conn.execute(text("UPDATE financial_transactions SET ledger_status = 'superseded', superseded_by_id = :n "
                      "WHERE id = :o"), {"n": new, "o": old})


@needs_template
def test_the_lane_holds_admitted_rows_on_their_dates_and_never_a_time_of_day():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ids = ledger(c, case)
            old = txn(c, case, ids, 0, tdate=date(2026, 3, 4), amount=1000)
            new = txn(c, case, ids, 1, tdate=date(2026, 3, 4), amount=1200)  # the correction's replacement row
            supersede(c, old, new)
            posted = txn(c, case, ids, 2, pdate=date(2026, 3, 6))
            value = txn(c, case, ids, 3, odate=date(2026, 3, 7), osrc="value")
            txn(c, case, ids, 4, tdate=date(2026, 3, 5), status="quarantined")
            txn(c, case, ids, 5, tdate=date(2026, 4, 1))  # outside the range
        with Session(engine) as s:
            out = money.lane(s, case, start_date=date(2026, 3, 1), end_date=date(2026, 3, 31))
        got = {i["transaction_id"]: i for i in out["items"]}
        assert out["total"] == 3 and out["returned"] == 3 and out["next_cursor"] is None
        assert old not in got and got[new]["amount_minor"] == 1200  # superseded row absent, corrected row present
        assert got[new]["date_basis"] == "transaction"
        assert got[posted]["date_basis"] == "posted" and "may be earlier" in got[posted]["date_words"]
        assert got[value]["date_basis"] == "value" and got[value]["day"] == date(2026, 3, 7)
        assert all(i["time_of_day"] is None for i in out["items"])
        assert all(not isinstance(i["day"], datetime) for i in out["items"])
        assert out["population"] == "admitted" and out["accounts"] == "all"


@needs_template
def test_a_place_is_attached_by_a_person_as_a_decision_and_replacing_it_keeps_the_first():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ids = ledger(c, case)
            t = txn(c, case, ids, 0, tdate=date(2026, 3, 4))
            gone = txn(c, case, ids, 1, tdate=date(2026, 3, 4))
            supersede(c, gone, t)
        with Session(engine) as s:
            with pytest.raises(money.MoneyError):
                money.attach(s, case, t, lat=38.9, lon=-77.0, radius_m=100, reason="  ", actor=ACTOR)
            with pytest.raises(money.MoneyError) as exc:
                money.attach(s, case, gone, lat=38.9, lon=-77.0, radius_m=100, reason="receipt", actor=ACTOR)
            assert exc.value.status == 409  # never on a superseded row
            first = money.attach(s, case, t, lat=38.9, lon=-77.0, radius_m=100, reason="receipt", actor=ACTOR)
            second = money.attach(s, case, t, lat=38.91, lon=-77.0, radius_m=50, reason="better receipt", actor=ACTOR)
            s.commit()
            assert second["replaced_place_id"] == first["place_id"]
            d = s.execute(text("SELECT decision, actor_email, before, after FROM adjudications WHERE subject_id = :t "
                               "ORDER BY subject_sequence"), {"t": t}).all()
            assert [r.decision for r in d] == ["attach_transaction_place"] * 2
            assert d[0].actor_email == "t@x.test" and d[1].before["place"] == {"lat": "38.9000000", "lon": "-77.0000000", "radius_m": 100}
            hist = money.history(s.connection(), case, t)
            assert len(hist) == 2 and hist[0]["removed_decision_id"] is not None and hist[1]["removed_decision_id"] is None
            out = money.lane(s, case, zone=ZoneInfo("America/New_York"))
            p = [i for i in out["items"] if i["transaction_id"] == t][0]["place"]
            assert p["radius_m"] == 50 and p["actor_name"] == "Test Person"
            # an attached place covers the whole local day, never a time inside it
            assert p["covers_start"].astimezone(timezone.utc) == datetime(2026, 3, 4, 5, tzinfo=timezone.utc)
            assert (p["covers_end"] - p["covers_start"]).total_seconds() == 86400
            money.remove(s, case, t, reason="wrong shop", actor=ACTOR)
            s.commit()
            assert money.lane(s, case)["items"][0]["place"] is None
            assert s.execute(text("SELECT count(*) FROM manual_changes WHERE kind = 'pattern_transaction_place'")
                             ).scalar() == 3


@needs_template
def test_money_and_manual_places_over_http():
    from tests.pattern_pg import api_client
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            other = make_case(c)
            ids = ledger(c, case)
            t = txn(c, case, ids, 0, tdate=date(2026, 3, 4))
            oids = ledger(c, other)
            foreign = txn(c, other, oids, 0, tdate=date(2026, 3, 4))
        with api_client(engine, case) as client:
            r = client.get("/api/pattern/%s/money" % case, params={"start_date": "2026-03-01",
                                                                    "end_date": "2026-03-31", "zone": "UTC"})
            assert r.status_code == 200 and r.json()["total"] == 1 and r.json()["items"][0]["time_of_day"] is None
            body = {"target": {"kind": "transaction", "transaction_id": str(t)}, "lat": 38.9, "lon": -77.0,
                    "radius_m": 75, "reason": "receipt"}
            assert client.post("/api/pattern/%s/places/manual" % case, json=body).status_code == 200
            body["target"]["transaction_id"] = str(foreign)
            assert client.post("/api/pattern/%s/places/manual" % case, json=body).status_code == 404
            body["target"]["transaction_id"] = str(t)
            body["radius_m"] = 0
            assert client.post("/api/pattern/%s/places/manual" % case, json=body).status_code == 422
            h = client.get("/api/pattern/%s/places/manual/%s" % (case, t)).json()
            assert h["total"] == 1 and h["items"][0]["actor_name"] == "synthetic"
