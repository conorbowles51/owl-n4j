"""Read the link analysis of a group of items the person marked "possibly related" (lx-overlaps E)."""
from uuid import UUID

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

CITE = {"financial_transaction": "txn://{id}", "phone_record": "rec://{id}"}


class RelationArgs(BaseModel):
    selection_id: str = Field(..., description="The id of the group the person marked with 'Corroborate'.")
    section: str = Field("overview", description=(
        "overview (one compact read of everything: start here), or candidates, no_links, analyses, items to page through "
        "the full rows"))
    offset: int = Field(0, ge=0)
    limit: int = Field(25, ge=1, le=100)


class DraftArgs(BaseModel):
    members: list[dict] = Field(..., min_length=1, max_length=500, description=(
        "The items to ask about, each {type, id, label?}: phone_record (a record uid), financial_transaction, evidence, "
        "graph_entity, person, phone, document_row."))
    kind: str = Field("in_contact", description="The question: in_contact, together, payment, every_time, who_else, statement, who_used, connected, behaviour_change or document.")
    text: str = Field(..., max_length=300, description="The question in plain words, as the person would read it.")
    people: list[str] = Field(default_factory=list, description="Person keys to ask about, if known.")


def cite_for(item: dict) -> str:
    form = CITE.get(item["type"])
    return form.format(id=item["id"]) if form else f"{item['type']}:{item['id']} ({item['label']})"


def make_relation_tools(context):
    from services.agent.tools import _financial_session
    from services.case_service import check_case_access
    from postgres.models.user import User
    from services import case_selections
    from services.relations import engine, runs
    from services.relations.sources import DbSources

    def get_relation_results(selection_id, section="overview", offset=0, limit=25):
        with (context.ledger_session_factory or _financial_session)() as db:
            user = db.get(User, UUID(str(context.user_id))) if context.user_id else None
            if user is None or not user.is_active:
                raise PermissionError("An active case reader is required.")
            check_case_access(db, UUID(str(context.case_id)), user, required_permission=("case", "view"))
            group = case_selections.describe(db, context.case_id, selection_id, member_limit=10**9)
            if group is None or group["group_type"] != "relation_query":
                return context.result("get_relation_results", {"error": "Not in this case."},
                                      summary="No such group in this case.", status="error", error="Not in this case.")
            run_id = runs.latest_for(db, context.case_id, selection_id)
            stored = runs.view(db, context.case_id, run_id)["result"] if run_id else None
            how = "stored run"
            if not stored:
                members = [{k: v for k, v in m.items() if k in ("type", "id", "label", "quote")} for m in group["members"]]
                stored, how = engine.run(DbSources(db, context.case_id), members), "run now, not saved"
        if section == "overview":
            cites = {i["ref"]: cite_for(i) for i in stored["items"]}
            who = lambda refs: [cites.get(r, r[:8]) for r in refs]  # noqa: E731
            cand = [{"kind": c["kind"], "strength": c["strength"], "members": who(c["members"]),
                     "why": " ".join(c["reasons"])[:260], "chance": (c["chance"].get("words") or "")[:220]}
                    for c in stored["candidates"]]
            nol = [{"members": who(n["members"]), "searched": "; ".join(n["searched"])[:200],
                    "out_of_reach": "; ".join(n["out_of_reach"])[:120]} for n in stored["no_links"]]
            data = {"selection_id": selection_id, "section": "overview", "says": stored["says"], "source": how,
                    "counts": stored["counts"], "baseline": stored["base"], "out_of_reach": stored["out_of_reach"],
                    "analyses": [{"id": a["id"], "pairs": a["pairs"], "found": a["found"]} for a in stored["analyses"]],
                    "items": [{"cite": cites[i["ref"]], "label": i["label"], "at": i["at"]} for i in stored["items"]],
                    "candidates": cand[:30], "candidates_total": len(cand),
                    "no_links": nol[:30], "no_links_total": len(nol),
                    "more": "Page the rest with section candidates or no_links, offset and limit." if len(cand) > 30 or len(nol) > 30 else None,
                    "rule": ("Strength comes from the stated rules, not from a model. Records show what occurs together, "
                             "never why. Nothing found is what was searched, not proof that no link exists.")}
            return context.result("get_relation_results", data,
                                  summary=f"Read the overview: {len(cand)} candidates and {len(nol)} pairs with no link ({how}).")
        rows = {"candidates": stored["candidates"], "no_links": stored["no_links"], "analyses": stored["analyses"],
                "items": [{**i, "cite": cite_for(i)} for i in stored["items"]]}.get(section)
        if rows is None:
            return context.result("get_relation_results", {"error": "section must be candidates, no_links, analyses or items"},
                                  summary="Unknown section.", status="error", error="Unknown section.")
        page = rows[offset:offset + limit]
        data = {"selection_id": selection_id, "section": section, "says": stored["says"], "source": how,
                "counts": stored["counts"], "baseline": stored["base"], "out_of_reach": stored["out_of_reach"],
                "total": len(rows), "returned": len(page), "offset": offset,
                "next_offset": offset + len(page) if offset + len(page) < len(rows) else None, "items": page,
                "cites": {i["ref"]: cite_for(i) for i in stored["items"]},
                "rule": ("Strength comes from the stated rules, not from a model. Records show what occurs together, "
                         "never why. Nothing found is what was searched, not proof that no link exists.")}
        return context.result("get_relation_results", data,
                              summary=f"Read {len(page)} of {len(rows)} {section.replace('_', ' ')} ({how}).")

    def draft_corroborate_question(members, text, kind="in_contact", people=()):
        """Save a drafted question for the person to open in the Corroborate composer. It is never run here."""
        from services.corroborate import questions
        with (context.ledger_session_factory or _financial_session)() as db:
            user = db.get(User, UUID(str(context.user_id))) if context.user_id else None
            if user is None or not user.is_active:
                raise PermissionError("An active case editor is required.")
            check_case_access(db, UUID(str(context.case_id)), user, required_permission=("case", "edit"))
            if questions.canonical(kind) is None:
                return context.result("draft_corroborate_question", {"error": "Unknown question kind."},
                                      summary="That question is not one Corroborate asks.", status="error", error="Unknown question kind.")
            try:
                group = runs.save_group(db, case_id=context.case_id, members=list(members), user=user, surface="assistant_draft",
                                        question={"kind": questions.canonical(kind), "text": text,
                                                  "chips": {"people": list(people), "what": "drafted by the assistant, not confirmed"}})
            except case_selections.SelectionError as exc:
                db.rollback()
                return context.result("draft_corroborate_question", {"error": str(exc)}, summary=str(exc), status="error", error=str(exc))
        link = f"/cases/{context.case_id}/agent?corro_draft={group['id']}"
        data = {"draft_id": group["id"], "items": group["member_count"], "left_out": group.get("left_out", 0), "open_link": link,
                "rule": ("This is a draft. Nothing has run. Tell the person it opens in the Corroborate composer, where they check "
                         "the question and press Corroborate. Give the link as [Open in Corroborate](" + link + ").")}
        return context.result("draft_corroborate_question", data,
                              summary=f"Drafted a question over {group['member_count']} items. Not run.")

    return [StructuredTool.from_function(
        func=draft_corroborate_question, name="draft_corroborate_question", args_schema=DraftArgs,
        description=("Draft a Corroborate question over items you have found, for the person to open in the composer. It never runs "
                     "the question: the person confirms it. Offer the returned link in your answer.")),
        StructuredTool.from_function(
        func=get_relation_results, name="get_relation_results", args_schema=RelationArgs,
        description=("Read the link analysis of a group the person marked with 'Corroborate': candidate links "
                     "(kind, members, strength by stated rule, the chance beside each), the pairs where nothing was found with "
                     "what was searched, each analysis run, and the items with their citations. Pages through "
                     "candidates, no_links, analyses and items. State counts before conclusions."))]
