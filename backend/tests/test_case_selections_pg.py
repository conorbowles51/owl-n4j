"""Corroborate's person, phone and document_row members are checked against the case in PostgreSQL-only SQL
(``ANY(CAST(:i AS uuid[]))``): one of another case is refused and one of this case kept. Opt-in: needs
LOUPE_TEST_PHONE_PG_TEMPLATE_URL (tests/phone_pg.py), as the head suite's scratch database gives."""
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from services import case_selections as CS
from tests import phone_pg

pytestmark = phone_pg.needs_template


def _person(c, case, name):
    pid = uuid.uuid4()
    c.execute(text("INSERT INTO case_profiles (id, case_id, profile_type, display_name, contacts, linkage_state, "
                   "status, needs_link_review, graph_entity_deleted, created_at, updated_at) VALUES (:d, :c, "
                   "'person', :n, '[]', 'unlinked', 'active', false, false, now(), now())"),
              {"d": pid, "c": case, "n": name})
    return str(pid)


def _file(c, case, name):
    fid = uuid.uuid4()
    c.execute(text("INSERT INTO evidence_files (id, case_id, original_filename, stored_path, sha256) "
                   "VALUES (:i, :c, :n, '/nowhere/x.pdf', :h)"), {"i": fid, "c": case, "n": name, "h": "c" * 64})
    return str(fid)


def test_people_phones_and_document_rows_of_another_case_are_refused():
    with phone_pg.fresh_engine() as engine:
        with engine.begin() as c:
            mine, other = phone_pg.make_case(c), phone_pg.make_case(c)
            p_mine, p_other = _person(c, mine, "Ann"), _person(c, other, "Bob")
            x_mine = str(phone_pg.make_extraction(c, mine, [], label="M1"))
            x_other = str(phone_pg.make_extraction(c, other, [], label="O1"))
            x_old = str(phone_pg.make_extraction(c, mine, [], label="M0", standing="superseded"))
            f_mine, f_other = _file(c, mine, "a.pdf"), _file(c, other, "b.pdf")
        with Session(engine) as db:
            case = uuid.UUID(str(mine))
            assert CS.MEMBER_CHECKS["person"](db, case, [p_mine, p_other, "not-a-uuid"]) == {p_mine}
            assert CS.MEMBER_CHECKS["phone"](db, case, [x_mine, x_other, x_old]) == {x_mine}
            rows = ["%s:3" % f_mine, "%s:4" % f_other, "%s:x" % f_mine, f_mine]
            assert CS.MEMBER_CHECKS["document_row"](db, case, rows) == {"%s:3" % f_mine}
            assert CS.MEMBER_CHECKS["person"](db, case, []) == set()
