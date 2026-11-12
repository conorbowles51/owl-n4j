"""All-cases mode for the agent, and the cross-case identifier index (agent-allcases; report rank 17, scenario 7).

Neil, 2026-11-01: "Maybe an option to operate across all user's cases could be useful but that shouldn't be by
default." So a run is scoped to its own case unless the person switches all-cases mode on for that message; a new
conversation starts with it off.

Which cases a run may read: the cases the person is a member of with case view permission, each confirmed by the
existing case access check (``check_case_access``) on every call, in that call's own read session. Membership is
required even for a super admin: all-cases mode never becomes a superuser read of every case on the server.

The identifier index is a read over columns the case data already keeps normalised, so it is never stale and needs no
refresh: ``financial_accounts.identifier_normalised`` (digits as printed) and ``iban``, and ``phone_identities``
(phone numbers in E.164, emails, app handles). An account number shorter than ``MIN_ACCOUNT_DIGITS`` digits (a last-4
or last-5 a statement prints) never matches: it cannot tell two accounts apart. It is listed instead as a faint
possible match (``possible``) when its digits end the looked-up number: the same last digits, which many accounts share
(Neil 2026-11-04: any match is mentioned, with its strength). Account numbers are shown masked.

A run scoped to one case learns only how many other cases the person may open hold the identifier, never which cases
and never their content.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Iterable

MIN_ACCOUNT_DIGITS = 6
MIN_HANDLE_CHARS = 3
MAX_MATCHES = 50  # matches listed per identifier, stated with their total
MIN_SUFFIX_DIGITS = 4  # a stored last-4 or last-5 is listed as a faint possible match; fewer digits say nothing

NOT_OPEN = "That case is not one you can open."


def mask_account(value: str | None) -> str | None:
    """An account number as the index shows it: the last four characters, the rest hidden."""
    digits = re.sub(r"\s+", "", value or "")
    if not digits:
        return None
    return ("••••" + digits[-4:]) if len(digits) > 4 else digits


def lookup_keys(identifier: str) -> dict[str, Any]:
    """What one identifier, as a person or model wrote it, is looked up as. Deterministic; no model involved.

    Returns {"accounts": [digits...], "ibans": [...], "phone_identities": [(kind, value_normalised)...],
    "handles": [casefolded...], "too_short": bool}.
    """
    from services.phone import numbers

    raw = (identifier or "").strip()
    keys: dict[str, Any] = {"accounts": [], "ibans": [], "phone_identities": [], "handles": [], "too_short": False}
    if not raw:
        return keys
    e = raw[7:] if raw.lower().startswith("mailto:") else raw
    if e.count("@") == 1 and "." in e.split("@")[1] and not any(c.isspace() for c in e):
        keys["phone_identities"].append(("email", e.lower()))
        return keys
    compact = re.sub(r"[\s\-./()]", "", raw)
    if re.fullmatch(r"[A-Za-z]{2}\d{2}[A-Za-z0-9]{8,30}", compact):
        keys["ibans"].append(compact.upper())
    unmasked = re.sub(r"[*•xX]", "", raw)
    if not any(c.isalpha() for c in unmasked.lstrip("+")) and re.fullmatch(r"[\d+()\-./ *•xX]+", raw):
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= MIN_ACCOUNT_DIGITS:
            keys["accounts"].append(digits)
        else:
            keys["too_short"] = True
            if len(digits) >= MIN_SUFFIX_DIGITS:
                keys["suffix"] = digits
        if 7 <= len(digits) <= 17:
            e164, _display, valid, _basis = numbers.parse(raw if unmasked == raw else digits)
            if valid:
                keys["phone_identities"].append(("phone", e164))
        return keys
    handle = raw.lower().lstrip("@")  # lower(), as the database compares
    if len(handle) >= MIN_HANDLE_CHARS:
        keys["handles"].append(handle)
    else:
        keys["too_short"] = True
    return keys


def openable_cases(db, user) -> dict[str, str]:
    """The cases the person is a member of with case view permission, id -> title, in ONE query (memberships joined to
    the cases). For a member with view permission, ``check_case_access`` asks exactly this: the case exists and the
    membership grants case.view (super admins get no more, since only member cases are listed). Before, every list,
    find and count ran check_case_access per membership (2 queries each) and then read the titles again (followups
    m110400240617959: 661 ms for 11 memberships under load). ``read_in_case`` keeps its per-call check (may_open)."""
    from postgres.models.case import Case
    from postgres.models.case_membership import CaseMembership
    from services.case_service import has_permission

    rows = (db.query(CaseMembership, Case.title).join(Case, Case.id == CaseMembership.case_id)
            .filter(CaseMembership.user_id == user.id).all())
    return {str(membership.case_id): title for membership, title in rows
            if has_permission(membership, "case", "view")}


def openable_case_ids(db, user) -> list[uuid.UUID]:
    """The ids of ``openable_cases``."""
    return [uuid.UUID(cid) for cid in openable_cases(db, user)]


def may_open(db, user, case_id) -> bool:
    """One case, checked now: a member with case view permission who passes the case access check."""
    from services.case_service import check_case_access, get_membership, has_permission

    try:
        cid = uuid.UUID(str(case_id))
    except (TypeError, ValueError):
        return False
    from postgres.models.case_membership import CaseMembership
    membership = (db.query(CaseMembership).filter(CaseMembership.case_id == cid, CaseMembership.user_id == user.id)
                  .populate_existing().first())
    if not has_permission(membership, "case", "view"):
        return False
    try:
        check_case_access(db, cid, user, required_permission=("case", "view"))
    except Exception:
        return False
    return True


def case_titles(db, case_ids: Iterable[uuid.UUID]) -> dict[str, str]:
    from postgres.models.case import Case

    ids = list(case_ids)
    if not ids:
        return {}
    return {str(c.id): c.title for c in db.query(Case).filter(Case.id.in_(ids)).all()}


def find_identifier(db, identifier: str, case_ids: list[uuid.UUID]) -> dict[str, Any]:
    """Every case among ``case_ids`` holding the identifier, with what holds it there (accounts masked)."""
    from sqlalchemy import and_, func, or_

    from postgres.models.financial import FinancialAccount
    from postgres.models.phone_identity import PhoneIdentity

    keys = lookup_keys(identifier)
    ids = [uuid.UUID(str(c)) for c in case_ids]
    matches: list[dict[str, Any]] = []
    if ids and (keys["accounts"] or keys["ibans"]):
        account_match = []
        if keys["accounts"]:
            account_match.append(FinancialAccount.identifier_normalised.in_(keys["accounts"]))
        if keys["ibans"]:
            account_match.append(func.upper(func.replace(func.coalesce(FinancialAccount.iban, ""), " ", ""))
                                 .in_(keys["ibans"]))
        rows = (db.query(FinancialAccount).filter(FinancialAccount.case_id.in_(ids), or_(*account_match))
                .order_by(FinancialAccount.case_id, FinancialAccount.id).all())
        for r in rows:
            matches.append({"case_id": str(r.case_id), "kind": "account", "record_id": str(r.id),
                            "value": mask_account(r.identifier_normalised or r.iban),
                            "institution": r.institution_name, "holder_name_as_printed": r.holder_name,
                            "account_type": r.account_type})
    if ids and (keys["phone_identities"] or keys["handles"]):
        clauses = [and_(PhoneIdentity.kind == kind, PhoneIdentity.value_normalised == value)
                   for kind, value in keys["phone_identities"]]
        if keys["handles"]:
            clauses.append(and_(PhoneIdentity.kind == "app_user",
                                func.lower(PhoneIdentity.value_normalised).in_(keys["handles"])))
        rows = (db.query(PhoneIdentity).filter(PhoneIdentity.case_id.in_(ids), or_(*clauses))
                .order_by(PhoneIdentity.case_id, PhoneIdentity.id).all())
        for r in rows:
            matches.append({"case_id": str(r.case_id), "kind": {"app_user": "handle"}.get(r.kind, r.kind),
                            "record_id": str(r.id), "value": r.value_display,
                            "seen_times_on_phones": r.sighting_count, "phones": r.phone_count})
    possible: list[dict[str, Any]] = []
    if ids and (keys["accounts"] or keys.get("suffix")):
        from sqlalchemy import literal
        # a looked-up last-4 or last-5: every account whose number ends with it
        ends = [FinancialAccount.identifier_normalised.like("%" + keys["suffix"])] if keys.get("suffix") else []
        ends += [and_(func.length(FinancialAccount.identifier_normalised).between(MIN_SUFFIX_DIGITS,
                                                                                  MIN_ACCOUNT_DIGITS - 1),
                     literal(d).like(func.concat("%", FinancialAccount.identifier_normalised)))
                for d in keys["accounts"]]
        rows = (db.query(FinancialAccount).filter(FinancialAccount.case_id.in_(ids), or_(*ends))
                .order_by(FinancialAccount.case_id, FinancialAccount.id).all())
        for r in rows:
            n = min(len(r.identifier_normalised), len(keys.get("suffix") or r.identifier_normalised))
            possible.append({"case_id": str(r.case_id), "kind": "account", "record_id": str(r.id),
                             "value": mask_account(r.identifier_normalised), "institution": r.institution_name,
                             "holder_name_as_printed": r.holder_name, "account_type": r.account_type,
                             "strength": "faint",
                             "how_well_matched": ["the same last %d digits, and no more digits to compare" % n],
                             "how_substantiated": [],
                             "limitation": "Many accounts share their last %d digits: a possibility to check, "
                                           "not a match." % n})
    cases = sorted({m["case_id"] for m in matches})
    return {"identifier_kinds_looked_up": _kinds(keys), "too_short": keys["too_short"], "cases": cases,
            "matches": matches, "possible": possible, "suffix": bool(keys.get("suffix"))}


def _kinds(keys: dict[str, Any]) -> list[str]:
    kinds = []
    if keys["accounts"] or keys["ibans"]:
        kinds.append("account number")
    for kind, _ in keys["phone_identities"]:
        kinds.append({"phone": "phone number", "email": "email"}[kind])
    if keys["handles"]:
        kinds.append("handle")
    return kinds


def other_case_count(db, user, home_case_id, identifier: str) -> dict[str, Any]:
    """For a case-scoped run: how many OTHER cases the person may open hold the identifier. Never which ones."""
    home = str(home_case_id)
    others = [c for c in openable_case_ids(db, user) if str(c) != home]
    found = find_identifier(db, identifier, others)
    n = len(found["cases"])
    if found["too_short"] and not found["identifier_kinds_looked_up"]:
        sentence = ("That identifier is too short to tell records apart (an account number needs %d digits or "
                    "more), so it was not looked up in other cases." % MIN_ACCOUNT_DIGITS)
    elif n:
        sentence = ("This identifier appears in %d other case%s you may open. Which cases, and what they hold, "
                    "are shown only in all-cases mode, which the person switches on." % (n, "" if n == 1 else "s"))
    else:
        sentence = "This identifier appears in no other case you may open."
    return {"identifier_kinds_looked_up": found["identifier_kinds_looked_up"], "other_cases": n,
            "sentence": sentence}


UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
TXN = re.compile(r"txn://(%s)" % UUID_RE)
DOC = re.compile(r"(?:doc|evidence)://([^\s)\]\"'>]+)")
REC = re.compile(r"rec://(%s)(#[^\s)\]\"'>]*)?" % UUID_RE)
CITE = re.compile(r"(?:txn|doc|rec|evidence)://[^\s)\]\"'>]+|/cases/[0-9a-fA-F-]{36}/[^\s)\]\"'>]+")


def payment_path(case_id: str, transaction_id: str) -> str:
    """A payment link that carries its case, read by the citation renderer as that case's row."""
    return f"/cases/{case_id}/financial?view=transactions&payment={transaction_id}"


def _doc_path(case_id: str, target: str) -> str:
    """A document citation of another case as that case's evidence page: on the file (and page) when it is cited by
    file id; the case's evidence list when it is cited by filename (a name is never resolved in the wrong case)."""
    head, _, tail = target.rstrip("/").rpartition("/")
    file_id, page = (head, tail) if head and tail.isdigit() else (target.rstrip("/"), "")
    if re.fullmatch(UUID_RE, file_id):
        return f"/cases/{case_id}/evidence?file={file_id}" + (f"&page={page}" if page else "")
    return f"/cases/{case_id}/evidence"


def case_qualify(value: Any, case_id: str, seen: set[str]) -> Any:
    """Rewrite citations in a result from another case (txn://, doc://, rec://) into links that carry that case, so
    no renderer resolves them in the conversation's own case; collect every citation the result holds into
    ``seen``."""
    if isinstance(value, str):
        out = TXN.sub(lambda m: payment_path(case_id, m.group(1)), value)
        out = DOC.sub(lambda m: _doc_path(case_id, m.group(1)), out)
        out = REC.sub(lambda m: f"/cases/{case_id}/records/{m.group(1)}{m.group(2) or ''}", out)
        seen.update(CITE.findall(out))
        return out
    if isinstance(value, dict):
        return {k: case_qualify(v, case_id, seen) for k, v in value.items()}
    if isinstance(value, list):
        return [case_qualify(v, case_id, seen) for v in value]
    return value


_LINK = re.compile(r"\[([^\]]*)\]\(\s*<?([^)>\s]+)>?\s*\)")


def name_cases_in_answer(answer: str, cited: dict[str, tuple[str, str]], home_case_id: str,
                         titles: dict[str, str | None] | None = None) -> str:
    """Every citation in the answer to a record of another case names its case beside the link.

    ``cited`` maps a citation href (as tools returned it) to (case_id, case title). A txn:// link the model wrote
    bare for another case's row is rewritten to the link that carries the case. Deterministic: the model may
    forget to name a case; this never does.
    """
    titles = {k.lower(): v for k, v in (titles or {}).items()}
    for cid, title in cited.values():
        titles.setdefault(cid.lower(), title)
    if not answer or not titles:
        return answer
    by_txn = {m.group(1).lower(): cid_title for href, cid_title in cited.items()
              for m in [re.search(r"payment=([0-9a-fA-F-]{36})", href)] if m}

    def fix(match: re.Match) -> str:
        label, href = match.group(1), match.group(2)
        owner = cited.get(href)
        txn = TXN.fullmatch(href)
        if txn and not owner:
            owner = by_txn.get(txn.group(1).lower())
            if owner:
                href = payment_path(owner[0], txn.group(1))
        if not owner:
            path = re.match(r"(?:https?://[^/\s]+)?/cases/([0-9a-fA-F-]{36})/", href)
            if path and path.group(1).lower() != str(home_case_id).lower():
                owner = (path.group(1), titles.get(path.group(1).lower()) or "another case")
        link = f"[{label}]({href})"
        if not owner or owner[0] == str(home_case_id):
            return link
        tail = answer[match.end(): match.end() + 120]
        if owner[1] and (owner[1] in label or owner[1] in tail[:len(owner[1]) + 12]):
            return link
        return f"{link} (case: {owner[1]})"

    return _LINK.sub(fix, answer)


# --------------------------------------------------------------------------------------------- agent tools

# Tools a cross-case read may run in another case: readers only. Artifact builders, clarification, drafting and
# proposal tools belong to the person's own case and conversation, so they never run against another case.
def _readable_elsewhere(name: str) -> bool:
    from services.agent.capabilities import types_for_tool
    return (name not in {'read_saved_agent_work', 'read_conversation_history', 'read_prior_result'}
            and bool(types_for_tool(name))
            and not name.startswith(("build_", "draft_", "propose_", "plan_", "create_", "revise_", "edit_", "append_")))


CROSS_CASE_TOOL_NAMES = ("identifier_in_other_cases", "list_my_cases", "find_identifier_across_cases",
                         "read_in_case")


def _user(db, user_id):
    from postgres.models.user import User

    return db.get(User, uuid.UUID(str(user_id))) if user_id else None


def make_cross_case_tools(context) -> list:
    """The cross-case tools for a run. Case-scoped run: only ``identifier_in_other_cases`` (a count). All-cases run
    (the person switched it on for this message): list, find and read across the cases the person may open."""
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    from services.agent.tools import EmptyArgs, _financial_session

    def session():
        return (context.ledger_session_factory or _financial_session)()

    def refused(name, message):
        return context.result(name, {"available": False, "reason": message}, summary=message, status="error",
                              error=message)

    class IdentifierArgs(BaseModel):
        identifier: str = Field(..., min_length=1, max_length=200,
                                description="An account number, IBAN, phone number, email or handle, as written.")

    def identifier_in_other_cases(identifier: str):
        if context.significant_scope:
            return refused("identifier_in_other_cases", "Other cases are out of scope while the agent is "
                           "restricted to the Significant layer.")
        with session() as db:
            user = _user(db, context.user_id)
            if user is None:
                return refused("identifier_in_other_cases", "Other cases cannot be checked for this run.")
            data = other_case_count(db, user, context.case_id, identifier)
        return context.result("identifier_in_other_cases", data, summary=data["sentence"])

    tools = [StructuredTool.from_function(
        func=identifier_in_other_cases, name="identifier_in_other_cases", args_schema=IdentifierArgs,
        description=("How many OTHER cases the person may open hold an account number, IBAN, phone number, email "
                     "or handle. Gives a count only, never which cases or what they hold."))]
    if not context.all_cases:
        return tools

    def list_my_cases():
        with session() as db:
            user = _user(db, context.user_id)
            titles = openable_cases(db, user) if user else {}
        cases = sorted(({"case_id": cid, "case_name": titles.get(cid), "this_case": cid == str(context.case_id)}
                        for cid in titles), key=lambda c: (not c["this_case"], c["case_name"] or ""))
        return context.result("list_my_cases", {"total": len(cases), "returned": len(cases), "cases": cases},
                              summary=f"{len(cases)} case(s) the person may open.")

    def find_identifier_across_cases(identifier: str):
        with session() as db:
            user = _user(db, context.user_id)
            titles = openable_cases(db, user) if user else {}
            ids = [uuid.UUID(cid) for cid in titles]
            found = find_identifier(db, identifier, ids)
        matches = found["matches"]
        for m in matches:
            m["case_name"] = titles.get(m["case_id"])
            context.cases_read.setdefault(m["case_id"], titles.get(m["case_id"]))
        shown = matches[:MAX_MATCHES]
        data = {"identifier_kinds_looked_up": found["identifier_kinds_looked_up"], "cases_searched": len(ids),
                "total": len(matches), "returned": len(shown), "matches": shown,
                "cases": [{"case_id": c, "case_name": titles.get(c), "this_case": c == str(context.case_id)}
                          for c in found["cases"]]}
        if len(matches) > len(shown):
            data["clipped"] = f"Showing {len(shown)} of {len(matches)} matches."
        possible = found["possible"]
        for m in possible:
            m["case_name"] = titles.get(m["case_id"])
            context.cases_read.setdefault(m["case_id"], titles.get(m["case_id"]))
        if possible:
            data["possible"] = possible[:MAX_MATCHES]
            data["possible_total"] = len(possible)
            one = len(possible) == 1
            data["possible_words"] = (
                ("%d account%s end%s with these digits: listed as faint possible matches, never as matches." % (
                    len(possible), "" if one else "s", "s" if one else ""))
                if found.get("suffix") else
                ("%d account%s print%s only last digits that end this number: listed as faint possible matches, "
                 "never as matches." % (len(possible), "" if one else "s", "s" if one else "")))
            if len(possible) > MAX_MATCHES:
                data["possible_clipped"] = f"Showing {MAX_MATCHES} of {len(possible)} possible matches."
        if found["too_short"] and not found["identifier_kinds_looked_up"]:
            data["reason"] = ("Too short to tell records apart (an account number needs %d digits or more); not "
                              "matched." % MIN_ACCOUNT_DIGITS) + (" Accounts ending with these digits are listed as "
                                                                  "faint possible matches." if possible else "")
        summary = (f"Found in {len(found['cases'])} of {len(ids)} case(s) the person may open "
                   f"({len(matches)} record(s)).")
        if possible:
            summary += " " + data["possible_words"]
        return context.result("find_identifier_across_cases", data, summary=summary)

    class ReadInCaseArgs(BaseModel):
        case_id: str = Field(..., description="A case_id from list_my_cases or find_identifier_across_cases.")
        tool: str = Field(..., description="The name of a read tool to run in that case, e.g. "
                                           "get_financial_transactions, search_documents, phone_find_people.")
        arguments: dict = Field(default_factory=dict, description="That tool's arguments.")

    other_contexts: dict[str, Any] = {}

    def read_in_case(case_id: str, tool: str, arguments: dict | None = None):
        from services.agent.tools import AgentToolContext, make_agent_tools

        name = "read_in_case"
        with session() as db:
            user = _user(db, context.user_id)
            allowed = bool(user) and may_open(db, user, case_id)
            title = case_titles(db, [uuid.UUID(str(case_id))]).get(str(case_id)) if allowed else None
        if not allowed:
            return refused(name, NOT_OPEN)
        cid = str(uuid.UUID(str(case_id)))
        if cid == str(context.case_id):
            return refused(name, "That is this conversation's own case: call the tool directly.")
        if not _readable_elsewhere(tool):
            return refused(name, f"{tool} cannot run in another case: only read tools can.")
        inner = other_contexts.get(cid)
        if inner is None:
            inner = AgentToolContext(case_id=cid, artifact_preference=context.artifact_preference,
                                     ledger_session_factory=context.ledger_session_factory, user_id=context.user_id)
            inner.tools_by_name = {t.name: t for t in make_agent_tools(inner)}
            other_contexts[cid] = inner
        inner.page_budget_chars = context.page_budget_chars
        target = inner.tools_by_name.get(tool)
        if target is None or not _readable_elsewhere(target.name):
            return refused(name, f"Unknown read tool: {tool}.")
        output = target.invoke(arguments or {})
        context.cases_read[cid] = title
        seen: set[str] = set()
        payload = output if isinstance(output, dict) else {"data": output}
        data = case_qualify(payload.get("data"), cid, seen)
        for href in seen:
            context.other_case_citations[href] = (cid, title)
        summary = f"[Case: {title}] {case_qualify(payload.get('summary') or '', cid, set())}"
        wrapped = {"case": {"case_id": cid, "case_name": title}, "tool": tool, "status": payload.get("status"),
                   "result": data}
        result = context.result(name, wrapped, summary=summary, status=payload.get("status") or "success",
                                error=payload.get("error"))
        if payload.get("phone_generation"):
            result["phone_generation"] = payload["phone_generation"]
        return result

    tools += [
        StructuredTool.from_function(
            func=list_my_cases, name="list_my_cases", args_schema=EmptyArgs,
            description="All-cases mode: list every case the person may open, this conversation's case first."),
        StructuredTool.from_function(
            func=find_identifier_across_cases, name="find_identifier_across_cases", args_schema=IdentifierArgs,
            description=("All-cases mode: which cases the person may open hold an account number (shown masked), "
                         "IBAN, phone number, email or handle, and the record holding it in each case.")),
        StructuredTool.from_function(
            func=read_in_case, name="read_in_case", args_schema=ReadInCaseArgs,
            description=("All-cases mode: run one read tool in another case the person may open. The result names "
                         "its case; cite its records with the links it returns and name the case beside each.")),
    ]
    return tools


ALL_CASES_PROMPT = """All-cases mode is ON for this message (the person switched it on). You may read the other cases the person may open, one tool call at a time:
- list_my_cases lists them; find_identifier_across_cases finds an account number, phone number, email or handle in all of them; read_in_case runs one read tool in one other case.
- Every record you cite from another case names its case beside the link, e.g. "[12 Mar payment](link) (case: <case name>)". Copy the links read_in_case returns exactly.
- An identifier in two cases is a lead, never a finding: say what each case holds and never merge the cases' parties or totals.
- Never add money from different cases into one total."""
