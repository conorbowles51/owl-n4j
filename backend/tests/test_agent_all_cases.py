"""All-cases mode and the cross-case identifier index (agent-allcases A to C).

Neil, 2026-11-01: "Maybe an option to operate across all user's cases could be useful but that shouldn't be by
default." Each test runs the tool layer the model calls (make_agent_tools with the run's case and person) on the
financial suite's SQLite harness: two matters holding the same account, plus a third the person is not a member of.
Every test fails on code that has no all-cases mode or no identifier index.
"""
import json
import uuid
from contextlib import contextmanager

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole, GlobalRole
from postgres.models.phone_identity import PhoneIdentity
from postgres.models.user import User
from tests.test_financial_duplicates import DuplicateTestCase

VIEW = {"case": {"view": True, "edit": False, "delete": False}}
NUMBER = "40112233"


class AllCasesTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[CaseMembership.__table__, PhoneIdentity.__table__])
        self.account.identifier_normalised = NUMBER
        self.other_account.identifier_normalised = NUMBER
        self.account.holder_name = "Synthetic holder A"
        self.other_account.holder_name = "Synthetic holder B"
        self.closed_case = Case(id=uuid.uuid4(), title="Matter C (not a member)", created_by_user_id=self.user.id,
                                owner_user_id=self.user.id)
        self.db.add(self.closed_case)
        self.db.commit()
        self.closed_account = self._account(self.closed_case.id)
        self.closed_account.identifier_normalised = NUMBER
        self.db.add(self.closed_account)
        for case in (self.case, self.other_case):
            self.db.add(CaseMembership(case_id=case.id, user_id=self.user.id, permissions=VIEW,
                                       membership_role=CaseMembershipRole.collaborator, added_by_user_id=self.user.id))
        self.db.commit()

    def phone_identity(self, case, kind, value, display=None):
        self.db.add(PhoneIdentity(id=uuid.uuid4(), case_id=case.id, identity_key="%s:%s" % (kind, value), kind=kind,
                                  value_normalised=value, value_display=display or value, sighting_count=3,
                                  phone_count=1))
        self.db.commit()

    def context(self, *, all_cases=False, user=None, case=None):
        from services.agent.tools import AgentToolContext

        @contextmanager
        def session():
            with self.SessionLocal() as s:
                yield s
        return AgentToolContext(case_id=str((case or self.case).id), ledger_session_factory=session,
                                user_id=str((user or self.user).id), all_cases=all_cases)

    def tools(self, ctx):
        from services.agent.tools import make_agent_tools
        return {t.name: t for t in make_agent_tools(ctx)}

    # -- A/B: off by default; the default run cannot read another case ------------------------------------------

    def test_all_cases_mode_is_off_by_default_and_a_scoped_run_has_no_other_case_reader(self):
        from services.agent.schemas import AgentMessageRequest
        request = AgentMessageRequest(message="q", case_id=self.case.id)
        self.assertFalse(request.all_cases)
        scoped = self.tools(self.context())
        self.assertIn("identifier_in_other_cases", scoped)
        for name in ("list_my_cases", "find_identifier_across_cases", "read_in_case"):
            self.assertNotIn(name, scoped)
        self.assertIn("read_in_case", self.tools(self.context(all_cases=True)))

    def test_a_case_scoped_run_answers_another_cases_account_as_not_in_this_case(self):
        out = self.tools(self.context())["get_statement_continuity"].invoke(
            {"account": str(self.other_account.id)})
        self.assertIn("not in this case", json.dumps(out))
        self.assertNotIn("Synthetic holder B", json.dumps(out))

    def test_the_scoped_prompt_has_no_all_cases_text_and_the_all_cases_prompt_says_so(self):
        from services.agent.graph import render_system_prompt
        kw = dict(case_id="c", significant=False, mandate_context_block="", artifact_preference="auto",
                  available_artifact_context="")
        self.assertNotIn("All-cases mode is ON", render_system_prompt(**kw))
        self.assertIn("All-cases mode is ON", render_system_prompt(**kw, all_cases=True))

    # -- C: the index, scoped: a count only ---------------------------------------------------------------------

    def test_a_scoped_run_learns_only_how_many_other_cases_it_may_open_hold_the_number(self):
        out = self.tools(self.context())["identifier_in_other_cases"].invoke({"identifier": "4011 2233"})
        self.assertEqual(out["data"]["other_cases"], 1)  # Matter B; Matter C is not the person's
        text = json.dumps(out)
        for leaked in (str(self.other_case.id), "Matter B", str(self.other_account.id), "Synthetic holder B",
                       str(self.closed_case.id)):
            self.assertNotIn(leaked, text)
        self.assertIn("1 other case you may open", out["summary"])

    def test_a_last_four_never_matches_across_cases(self):
        out = self.tools(self.context())["identifier_in_other_cases"].invoke({"identifier": "2233"})
        self.assertEqual(out["data"]["other_cases"], 0)
        self.assertIn("too short", out["summary"])

    def test_phone_numbers_emails_and_handles_are_indexed(self):
        self.phone_identity(self.other_case, "phone", "+12015550104", "+1 201-555-0104")
        self.phone_identity(self.other_case, "email", "mule@example.test")
        self.phone_identity(self.other_case, "app_user", "shadowpay")
        self.phone_identity(self.closed_case, "phone", "+12015550104")
        tool = self.tools(self.context())["identifier_in_other_cases"]
        for written in ("(201) 555-0104", "+1 201 555 0104", "Mule@Example.test", "@ShadowPay"):
            self.assertEqual(tool.invoke({"identifier": written})["data"]["other_cases"], 1, written)
        self.assertEqual(tool.invoke({"identifier": "+12015550199"})["data"]["other_cases"], 0)

    # -- A/C: all-cases mode ----------------------------------------------------------------------------------

    def test_all_cases_lists_only_member_cases_even_for_a_super_admin(self):
        admin = User(id=uuid.uuid4(), email="admin@example.test", name="Admin", password_hash="x",
                     global_role=GlobalRole.super_admin, is_active=True)
        self.db.add(admin)
        self.db.add(CaseMembership(case_id=self.case.id, user_id=admin.id, permissions=VIEW,
                                   membership_role=CaseMembershipRole.collaborator, added_by_user_id=self.user.id))
        self.db.commit()
        for user, expected in ((self.user, {"Matter A", "Matter B"}), (admin, {"Matter A"})):
            out = self.tools(self.context(all_cases=True, user=user))["list_my_cases"].invoke({})
            self.assertEqual({c["case_name"] for c in out["data"]["cases"]}, expected)

    def test_listing_cases_reads_memberships_and_titles_in_one_query_however_many_cases(self):
        # followups m110400240617959: check_case_access per membership made each list/find/count linear in cases.
        from sqlalchemy import event

        def selects(tool, args):
            seen = []
            listener = lambda conn, cursor, statement, *rest: seen.append(statement)
            event.listen(self.engine, "before_cursor_execute", listener)
            try:
                out = self.tools(self.context(all_cases=True))[tool].invoke(args)
            finally:
                event.remove(self.engine, "before_cursor_execute", listener)
            self._seen = [s for s in seen if s.lstrip().upper().startswith("SELECT")]
            return out, len(self._seen)

        _, before = selects("list_my_cases", {})
        _, find_before = selects("find_identifier_across_cases", {"identifier": NUMBER})
        for n in range(6):
            case = Case(id=uuid.uuid4(), title=f"Matter extra {n}", created_by_user_id=self.user.id,
                        owner_user_id=self.user.id)
            self.db.add(case)
            self.db.flush()
            self.db.add(CaseMembership(case_id=case.id, user_id=self.user.id, permissions=VIEW if n else {},
                                       membership_role=CaseMembershipRole.collaborator, added_by_user_id=self.user.id))
        self.db.commit()
        out, after = selects("list_my_cases", {})
        self.assertEqual(after, before)
        [membership_read] = [s for s in self._seen if "case_memberships" in s]  # one read, joined to the cases
        self.assertIn("JOIN cases", membership_read)
        names = {c["case_name"] for c in out["data"]["cases"]}
        self.assertEqual(len(names), 2 + 5)  # the membership without case.view is not listed
        self.assertNotIn("Matter extra 0", names)
        _, find_after = selects("find_identifier_across_cases", {"identifier": NUMBER})
        self.assertEqual(find_after, find_before)

    def test_find_names_each_case_and_masks_account_numbers(self):
        ctx = self.context(all_cases=True)
        out = self.tools(ctx)["find_identifier_across_cases"].invoke({"identifier": NUMBER})
        data = out["data"]
        self.assertEqual({m["case_name"] for m in data["matches"]}, {"Matter A", "Matter B"})
        self.assertEqual({m["value"] for m in data["matches"]}, {"••••2233"})
        self.assertNotIn(NUMBER, json.dumps(data))
        self.assertNotIn(str(self.closed_case.id), json.dumps(out))
        self.assertEqual(data["cases_searched"], 2)

    def test_read_in_case_checks_access_per_call_and_names_the_case(self):
        ctx = self.context(all_cases=True)
        read = self.tools(ctx)["read_in_case"]
        ok = read.invoke({"case_id": str(self.other_case.id), "tool": "get_statement_continuity",
                          "arguments": {"account": str(self.other_account.id)}})
        self.assertEqual(ok["data"]["case"], {"case_id": str(self.other_case.id), "case_name": "Matter B"})
        self.assertTrue(ok["summary"].startswith("[Case: Matter B]"))
        self.assertNotIn("not in this case", json.dumps(ok["data"]["result"]))
        self.assertEqual(ctx.cases_read, {str(self.other_case.id): "Matter B"})
        closed = read.invoke({"case_id": str(self.closed_case.id), "tool": "get_statement_continuity",
                              "arguments": {"account": str(self.closed_account.id)}})
        self.assertEqual(closed["status"], "error")
        self.assertIn("not one you can open", closed["summary"])
        self.assertNotIn("Matter C", json.dumps(closed))
        # Membership removed mid-run: the next call is refused (checked per call, not once per run).
        self.db.query(CaseMembership).filter(CaseMembership.case_id == self.other_case.id).delete()
        self.db.commit()
        again = read.invoke({"case_id": str(self.other_case.id), "tool": "get_statement_continuity",
                             "arguments": {"account": str(self.other_account.id)}})
        self.assertEqual(again["status"], "error")

    def test_read_in_case_runs_readers_only(self):
        read = self.tools(self.context(all_cases=True))["read_in_case"]
        for tool in ("build_table_artifact_from_rows", "request_clarification", "read_in_case",
                     "propose_judgement_call", "propose_workspace_entry"):
            out = read.invoke({"case_id": str(self.other_case.id), "tool": tool, "arguments": {}})
            self.assertEqual(out["status"], "error", tool)

    # -- A: every cited record names its case -----------------------------------------------------------------

    def test_other_case_payment_links_carry_their_case_and_the_answer_names_it(self):
        from services.agent.all_cases import case_qualify, name_cases_in_answer
        txn, other = str(uuid.uuid4()), str(self.other_case.id)
        seen = set()
        data = case_qualify({"rows": [{"cite": "txn://%s" % txn}]}, other, seen)
        link = "/cases/%s/financial?view=transactions&payment=%s" % (other, txn)
        self.assertEqual(data["rows"][0]["cite"], link)
        cited = {href: (other, "Matter B") for href in seen}
        own = str(uuid.uuid4())
        answer = ("Paid [12 Mar](%s) and also [bare](txn://%s); this case's [row](txn://%s)." % (link, txn, own))
        out = name_cases_in_answer(answer, cited, str(self.case.id))
        self.assertEqual(out.count("(case: Matter B)"), 2)
        self.assertIn("[bare](%s)" % link, out)
        self.assertIn("[row](txn://%s)." % own, out)
        named = "See [12 Mar](%s) (case: Matter B)." % link
        self.assertEqual(name_cases_in_answer(named, cited, str(self.case.id)), named)

    def test_the_run_record_lists_the_cases_read(self):
        from types import SimpleNamespace

        from services.agent.run_record_export import _cases_read
        run = SimpleNamespace(case_id=self.case.id)
        meta = {"all_cases": True, "cases_read": [{"case_id": str(self.case.id)},
                                                  {"case_id": str(self.other_case.id), "case_name": "x"}]}
        rows = _cases_read(self.db, run, meta)
        self.assertEqual([(r["case_name"], r["this_case"]) for r in rows], [("Matter A", True), ("Matter B", False)])
        self.assertEqual([r["case_name"] for r in _cases_read(self.db, run, {})], ["Matter A"])

    # -- review fixes -----------------------------------------------------------------------------------------

    def test_document_and_phone_citations_of_another_case_open_in_that_case(self):
        from services.agent.all_cases import case_qualify
        other, fid, uid = str(self.other_case.id), str(uuid.uuid4()), str(uuid.uuid4())
        seen = set()
        out = case_qualify(["doc://%s/4" % fid, "doc://%s" % fid, "doc://March%%20statement.pdf/2",
                            "rec://%s#body" % uid], other, seen)
        self.assertEqual(out, ["/cases/%s/evidence?file=%s&page=4" % (other, fid),
                               "/cases/%s/evidence?file=%s" % (other, fid), "/cases/%s/evidence" % other,
                               "/cases/%s/records/%s#body" % (other, uid)])
        self.assertTrue(all("://" not in href for href in seen))

    def test_a_link_into_another_case_is_named_even_when_no_read_in_this_run_cited_it(self):
        from services.agent.all_cases import name_cases_in_answer
        other = str(self.other_case.id)
        answer = "See [row](/cases/%s/financial?view=transactions&payment=%s)." % (other, uuid.uuid4())
        out = name_cases_in_answer(answer, {}, str(self.case.id), titles={other: "Matter B"})
        self.assertIn("(case: Matter B)", out)

    def test_masked_account_numbers_are_read_as_numbers_not_handles(self):
        from services.agent.all_cases import lookup_keys
        self.assertEqual(lookup_keys("XXXX2233")["accounts"], [])
        self.assertTrue(lookup_keys("XXXX2233")["too_short"])
        self.assertEqual(lookup_keys("xx40112233")["accounts"], [NUMBER])
        self.assertEqual(lookup_keys("xx40112233")["handles"], [])

    def test_the_run_record_counts_reads_of_a_run_that_stopped_before_its_end(self):
        from types import SimpleNamespace

        from services.agent.run_record_export import _cases_read
        calls = [SimpleNamespace(name="read_in_case", status="success", arguments={"case_id": str(self.other_case.id)}),
                 SimpleNamespace(name="read_in_case", status="error", arguments={"case_id": str(self.closed_case.id)})]
        run = SimpleNamespace(case_id=self.case.id, tool_calls=calls)
        self.assertEqual([r["case_name"] for r in _cases_read(self.db, run, {"all_cases": True})],
                         ["Matter A", "Matter B"])

    def test_a_case_only_message_never_sees_an_earlier_all_cases_answer(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from services.agent.service import WITHHELD_ALL_CASES_ANSWER, AgentService
        msgs = [SimpleNamespace(role="user", content="q1", run=None),
                SimpleNamespace(role="assistant", content="Matter B paid X", run=SimpleNamespace(
                    extra_metadata={"all_cases": True})),
                SimpleNamespace(role="assistant", content="own case", run=SimpleNamespace(extra_metadata={}))]
        with patch("services.agent.service.storage.recent_messages", return_value=msgs):
            scoped = AgentService()._build_history(None, thread=SimpleNamespace(id=1))
            wide = AgentService()._build_history(None, thread=SimpleNamespace(id=1), all_cases=True)
        self.assertEqual([m.content for m in scoped], ["q1", WITHHELD_ALL_CASES_ANSWER, "own case"])
        self.assertEqual(wide[1].content, "Matter B paid X")
