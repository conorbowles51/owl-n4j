"""07 CO-9a and CO-9b; 05 15.8 test 6: a link to a record of a replaced report says so and offers the record with
the equal natural key in the report that replaced it, or says none has it. Invented data only."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.phone import replaced_links as R
from services.phone_analysis import extraction_comparison as E
from tests.phone_analysis_fixture import record
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

OWNER, ANA = "phone:+12025550100", "phone:+12025550111"


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def msg(t, body):
    return dict(kind="message", instant=t, body=body, thread="t", direction="incoming",
                parties=[(ANA, "sender", False, None, None), (OWNER, "recipient", True, None, None)])


def _replace(c, old, new):
    c.execute(text("UPDATE phone_extractions SET standing = 'superseded', superseded_at = now() WHERE id = :o"),
              {"o": old})
    c.execute(text("UPDATE phone_extractions SET supersedes_id = :o WHERE id = :n"), {"o": old, "n": new})


@needs_template
def test_keys_of_any_report_equal_approach_12_keys_on_a_report_in_use(engine):
    with engine.begin() as c:
        case = make_case(c)
        ext, _ = phone(c, case, events=[msg(at(2023, 1, 2, 9), "one"), msg(at(2023, 1, 2, 9), "one"),
                                        msg(at(2023, 1, 3, 9), "two")])
        record(c, case, ext, 900, "Note", texts=[("Title", "synthetic note")])
    with engine.connect() as c:
        assert R.keys_any(c, str(ext)) == dict(E._keys(c, str(ext)))


@needs_template
def test_a_replaced_record_offers_the_equal_key_record_or_says_none_has_it(engine):
    """15.8 test 6: after Replace, a record of the older report offers the record with the equal key in the newer
    one; a record with no equal key offers none and says so; a record of the report in use is not replaced."""
    with engine.begin() as c:
        case = make_case(c)
        old, old_evs = phone(c, case, label="C1", events=[msg(at(2023, 1, 2, 9), "kept"),
                                                          msg(at(2023, 1, 3, 9), "only in the older")])
        new, new_evs = phone(c, case, label="C1 again", events=[msg(at(2023, 1, 2, 9), "kept"),
                                                                msg(at(2023, 3, 1, 9), "new")])
        _replace(c, old, new)
    kept_old, gone = old_evs[0]["record_uid"], old_evs[1]["record_uid"]
    kept_new = new_evs[0]["record_uid"]
    with engine.connect() as c:
        out = R.replacements(c, case, [kept_old, gone, kept_new])
    assert out[str(kept_old)] == {"replaced": True, "words": "%s %s" % (R.REPLACED, R.NEWER_HOLDS),
                                  "newer_extraction_id": str(new), "newer_record_uid": str(kept_new),
                                  "newer_record_type": out[str(kept_old)]["newer_record_type"]}
    assert out[str(kept_old)]["newer_record_type"]
    assert out[str(gone)]["replaced"] and out[str(gone)]["newer_record_uid"] is None
    assert out[str(gone)]["words"] == "%s %s" % (R.REPLACED, R.NEWER_LACKS)
    assert out[str(kept_new)]["replaced"] is False and out[str(kept_new)]["words"] is None


@needs_template
def test_a_chain_of_replaces_reaches_the_report_in_use(engine):
    with engine.begin() as c:
        case = make_case(c)
        a, a_evs = phone(c, case, label="C1", events=[msg(at(2023, 1, 2, 9), "kept")])
        b, _ = phone(c, case, label="C1 b", events=[msg(at(2023, 1, 2, 9), "kept")])
        d, d_evs = phone(c, case, label="C1 c", events=[msg(at(2023, 1, 2, 9), "kept")])
        _replace(c, a, b)
        _replace(c, b, d)
    with engine.connect() as c:
        out = R.replacements(c, case, [a_evs[0]["record_uid"]])
    assert out[str(a_evs[0]["record_uid"])]["newer_record_uid"] == str(d_evs[0]["record_uid"])
    assert out[str(a_evs[0]["record_uid"])]["newer_extraction_id"] == str(d)


@needs_template
def test_a_replaced_report_with_no_report_in_use_offers_none(engine):
    with engine.begin() as c:
        case = make_case(c)
        old, evs = phone(c, case, label="C1", events=[msg(at(2023, 1, 2, 9), "kept")])
        c.execute(text("UPDATE phone_extractions SET standing = 'superseded', superseded_at = now() WHERE id = :o"),
                  {"o": old})
    with engine.connect() as c:
        out = R.replacements(c, case, [evs[0]["record_uid"]])
    assert out[str(evs[0]["record_uid"])]["words"] == "%s %s" % (R.REPLACED, R.NONE_IN_USE)


@needs_template
def test_a_part_of_a_record_is_not_claimed_absent(engine):
    """A record inside another (an attachment) has no key of its own: the link says it is not matched, never that
    the newer report lacks it."""
    with engine.begin() as c:
        case = make_case(c)
        old, _ = phone(c, case, label="C1", events=[msg(at(2023, 1, 2, 9), "kept")])
        new, _ = phone(c, case, label="C1 again", events=[msg(at(2023, 1, 2, 9), "kept")])
        record(c, case, old, 900, "Note", texts=[("Title", "synthetic note")])
        child = record(c, case, old, 901, "Attachment", texts=[("Filename", "synthetic.txt")], parent=900)
        _replace(c, old, new)
    with engine.connect() as c:
        out = R.replacements(c, case, [child])
    assert out[str(child)]["words"] == "%s %s" % (R.REPLACED, R.NOT_KEYED)


def test_more_than_the_limit_is_refused_with_the_count():
    with pytest.raises(R.TooMany, match="501 were asked"):
        R.replacements(None, "c", ["u%d" % i for i in range(R.MAX_RECORDS + 1)])
