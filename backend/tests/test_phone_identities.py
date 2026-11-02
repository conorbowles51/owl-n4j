"""02-U9 (brief items K and L): identities, sightings, each phone's names and the owner (02 sections 8.5, 8.6).

Synthetic phones only. Rules NM-1 to NM-5 and OW-1 to OW-6; a WhatsApp id and its number give one identity.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from services.phone import identities, registry, sweep
from services.phone.mappings import apply, loader
from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template, refs
from tests.test_phone_mappings import CALL, hooks, write  # noqa: F401 (fixture)

ANA = "phone:+12025550143"
OWNER = "phone:+12025550100"
EARLY = datetime(2023, 1, 5, 12, 0, tzinfo=timezone.utc)
LATE = datetime(2023, 6, 5, 12, 0, tzinfo=timezone.utc)


def _stamp(ordinal, mt, field, instant):
    return {"o": ordinal, "bp": "0.0", "mt": mt, "fn": field, "ot": instant.isoformat(), "i": instant,
            "os": "explicit", "off": 0, "ft": None, "lw": None}


def _contact(top, name, number, modified=None):
    fields = []
    if modified is not None:
        fields.append(fld("TimeModified", ("TimeStamp", modified.isoformat())))
    fields += [fld("Name", ("String", name)), refs("Entries", top + 1)]
    card = model("Contact", fields)
    entry = model("PhoneNumber", [fld("Value", ("String", number)), fld("Category", ("String", "Mobile"))])
    return [(top, None, top, card), (top + 1, top, top, entry)], ([_stamp(top, "Contact", "TimeModified", modified)]
                                                                  if modified else [])


def _call(top, parties, direction="Outgoing"):
    """parties: [(identifier, name, is_owner)]"""
    recs = []
    call = model("Call", [fld("TimeStamp", ("TimeStamp", EARLY.isoformat())),
                          fld("Direction", ("ModelDirections", direction)),
                          refs("Parties", *[top + 1 + i for i in range(len(parties))])])
    recs.append((top, None, top, call))
    for i, (ident, name, owner) in enumerate(parties):
        f = [fld("Identifier", ("String", ident))] if ident is not None else []
        if name:
            f.append(fld("Name", ("String", name)))
        if owner is not None:
            f.append(fld("IsPhoneOwner", ("Boolean", "True" if owner else "False")))
        recs.append((top + 1 + i, top, top, model("Party", f)))
    return recs, [_stamp(top, "Call", "TimeStamp", EARLY)]


def _phone(c, case, parts, metadata=None):
    records, stamps = [], []
    for r, s in parts:
        records += r
        stamps += s
    return make_extraction(c, case, records, timestamps=stamps, metadata=metadata)


def _phone_a(c, case):
    return _phone(c, case, [
        _contact(0, "Synthetic Ana", "+12025550143", EARLY),
        _contact(2, "Ana Work", "(202) 555-0143", LATE),
        _contact(4, "+1 202 555 0143", "+12025550143"),        # the number echoed back as a name (NM-4)
        _call(6, [("+12025550100", "Synthetic Owner", True), ("12025550143@s.whatsapp.net", "Ana WA", False)]),
    ], metadata={"MSISDN": "+12025550100"})


def _rows(conn, sql, **kw):
    return [tuple(r) for r in conn.execute(text(sql), kw)]


def test_an_identifier_echoed_back_is_not_a_name():
    assert identities.is_echo("+1 (202) 555-0143")
    assert identities.is_echo("12025550143@s.whatsapp.net")
    assert identities.is_echo("120363000000000000@g.us")
    assert identities.is_echo("someone", raw="someone")
    assert identities.is_echo("  ")
    assert not identities.is_echo("Synthetic Ana")
    assert not identities.is_echo("Room 101")


@needs_template
def test_a_whatsapp_id_and_its_number_give_one_identity_with_each_phones_names(hooks):
    write(str(hooks), CALL)
    identities.install()
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            a = _phone_a(c, case)
            b = _phone(c, case, [_contact(0, "Mum", "+12025550143", EARLY)])
        assert sweep.interpret_one(engine, a)["status"] == "done"
        assert sweep.interpret_one(engine, b)["status"] == "done"
        with engine.connect() as c:
            ids = _rows(c, "SELECT identity_key, kind, sighting_count, phone_count FROM phone_identities WHERE "
                           "case_id = :c ORDER BY 1", c=case)
            assert (ANA, "phone", 5, 2) in ids  # 3 cards and the JID party on A, 1 card on B
            assert not any(k.startswith("app:whatsapp:jid") for k, *_ in ids)
            ctx = _rows(c, "SELECT context, count(*) FROM pv_identity_sighting WHERE extraction_id = :e AND "
                           "identity_key = :k GROUP BY 1 ORDER BY 1", e=a, k=ANA)
            assert ctx == [("listed_on_card", 3), ("party", 1)]
            names = _rows(c, "SELECT extraction_id, name, basis, occurrences, is_phone_name FROM pv_identity_name "
                             "WHERE identity_key = :k ORDER BY 1, 2", k=ANA)
            on_a = sorted((n, bs, occ, ph) for e, n, bs, occ, ph in names if e == a)
            # NM-2: one name each, the tie goes to the latest TimeModified; NM-4: the echoed number is no name
            assert on_a == [("Ana WA", "name_in_record", 1, False), ("Ana Work", "contact", 1, True),
                            ("Synthetic Ana", "contact", 1, False)]
            # NM-1, NM-5: the other phone's name is kept beside it, each with its phone
            assert [(n, ph) for e, n, bs, occ, ph in names if e == b] == [("Mum", True)]


@needs_template
def test_with_no_contact_name_the_most_frequent_name_in_records_is_the_phones_name(hooks):
    write(str(hooks), CALL)
    identities.install()
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            e = _phone(c, case, [_call(0, [("+12025550143", "Name One", False)]),
                                 _call(2, [("+12025550143", "Name Two", False)]),
                                 _call(4, [("+12025550143", "Name Two", False)]),
                                 _call(6, [("+12025550199", None, False)])])
        sweep.interpret_one(engine, e)
        with engine.connect() as c:
            names = _rows(c, "SELECT name, occurrences, is_phone_name FROM pv_identity_name WHERE extraction_id = :e "
                             "AND identity_key = :k ORDER BY 1", e=e, k=ANA)
            assert names == [("Name One", 1, False), ("Name Two", 2, True)]  # NM-3
            assert _rows(c, "SELECT count(*) FROM pv_identity_name WHERE identity_key = 'phone:+12025550199'") == [(0,)]


@needs_template
def test_the_owner_from_the_header_with_every_candidate_kept(hooks):
    write(str(hooks), CALL)
    identities.install()
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            a = _phone_a(c, case)
        sweep.interpret_one(engine, a)
        with engine.connect() as c:
            o = identities.owner(c, a)
            assert o["computed"] == {"identity_key": OWNER, "tier": 1, "basis": "extracted"}  # OW-1
            assert o["owner_identity_keys"] == [OWNER] and o["owner_basis"] == "extracted"
            numbers = sorted((x["identity_key"], x["tier"], x["occurrences"]) for x in o["candidates"]
                             if x["candidate_kind"] == "number")
            assert numbers == [(OWNER, 1, 1), (OWNER, 2, 1)]  # OW-3: both tiers stored
            assert [x["name"] for x in o["candidates"] if x["candidate_kind"] == "name"] == ["Synthetic Owner"]
            # OW-6: the owner's other identities are listed, never merged into the owner
            assert all(x["identity_key"] != OWNER for x in o["candidates"] if x["candidate_kind"] == "account")


@needs_template
def test_no_owner_evidence_still_interprets_and_an_owner_decision_overrides(hooks):
    write(str(hooks), CALL)
    identities.install()
    saved = identities._hooks["owner_decision"]
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            e = _phone(c, case, [_call(0, [("+12025550143", None, None)]), _call(2, [("+12025550101", None, None)])])
            tie = _phone(c, case, [_call(0, [("+12025550102", None, True)]), _call(2, [("+12025550101", None, True)])])
        assert sweep.interpret_one(engine, e)["status"] == "done"
        sweep.interpret_one(engine, tie)
        with engine.connect() as c:
            o = identities.owner(c, e)
            assert o["computed"]["basis"] == "unidentified" and o["owner_identity_keys"] == []  # OW-2
            implicit = _rows(c, "SELECT count(*) FROM phone_participations p JOIN phone_interpretation_state s ON "
                                "s.extraction_id = p.extraction_id AND s.generation = p.generation WHERE "
                                "p.extraction_id = :e AND p.role = 'owner_implicit'", e=e)
            assert implicit == [(2,)]
            # OW-4: equal counts, the lower E.164 string wins
            assert identities.owner(c, tie)["computed"] == {"identity_key": "phone:+12025550101", "tier": 2,
                                                            "basis": "inferred"}
        try:  # OW-5: a decision overrides and the computed candidates stay visible
            identities.register_owner_decision(lambda conn, ext: {"identity_keys": ["phone:+12025550102"],
                                                                  "decision_id": "d1", "by": "A Person"}
                                               if str(ext) == str(tie) else None)
            with engine.connect() as c:
                o = identities.owner(c, tie)
                assert o["owner_basis"] == "manual" and o["owner_identity_keys"] == ["phone:+12025550102"]
                assert o["computed"]["identity_key"] == "phone:+12025550101"
                assert len([x for x in o["candidates"] if x["candidate_kind"] == "number"]) == 2
        finally:
            identities._hooks["owner_decision"] = saved


@needs_template
def test_an_identity_no_longer_seen_keeps_its_row_at_zero(hooks):
    write(str(hooks), CALL)
    identities.install()
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            b = _phone(c, case, [_contact(0, "Mum", "+12025550143", EARLY)])
        sweep.interpret_one(engine, b)
        with engine.begin() as c:
            c.execute(text("UPDATE phone_extractions SET standing = 'superseded' WHERE id = :e"), {"e": b})
            other = _phone(c, case, [_contact(0, "Someone", "+12025550199", EARLY)])
        sweep.interpret_one(engine, other)
        with engine.connect() as c:
            assert _rows(c, "SELECT sighting_count, phone_count FROM phone_identities WHERE case_id = :c AND "
                            "identity_key = :k", c=case, k=ANA) == [(0, 0)]
