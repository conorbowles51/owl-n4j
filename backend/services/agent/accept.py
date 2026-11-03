"""A person accepts an agent answer into a dossier assessment (docs/cellebrite/07 sections 6.3 and 7.1, CO-18).

The agent never adds to a dossier itself. When a person accepts one of its answers, the assessment is stored
``ai_assisted``, names the answer (``agent_message_id``) and shows "Read by <model>, accepted by <name>". The phone
records the answer cites (its ``rec://`` links) become the assessment's supporting links, each checked against the
case; a cited record that is not in the case is not linked and is counted in the reply, never dropped silently.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select

REC = re.compile(r"rec://([0-9a-fA-F-]{36})")
MAX_LINKS = 100


class AcceptError(ValueError):
    pass


def cited_records(content: str) -> list[str]:
    seen: list[str] = []
    for m in REC.finditer(content or ""):
        uid = m.group(1).lower()
        if uid not in seen:
            seen.append(uid)
    return seen


def accept_answer_into_assessment(db, *, case_id, message_id, dossier_id, category: str, user) -> dict:
    from postgres import link_types
    from postgres.models.agent import AgentMessage, AgentThread
    from postgres.models.case_profile import CaseProfile
    from services import dossier_service
    row = db.execute(select(AgentMessage, AgentThread.case_id).join(AgentThread, AgentThread.id == AgentMessage.thread_id)
                     .where(AgentMessage.id == message_id)).first()
    if row is None or str(row[1]) != str(case_id):
        raise LookupError("This answer is not in this case.")
    message = row[0]
    if message.role != "assistant":
        raise AcceptError("Only an answer from the agent can be accepted this way.")
    content = (message.content or "").strip()
    if not content:
        raise AcceptError("This answer has no text to accept.")
    dossier = db.get(CaseProfile, dossier_id)
    if dossier is None or str(dossier.case_id) != str(case_id):
        raise LookupError("This dossier is not in this case.")
    links, refused = [], []
    cited = cited_records(content)
    for uid in cited:
        try:
            link_types.resolve_phone_target(db, uuid.UUID(str(case_id)), "phone_record", uid)
        except link_types.PhoneLinkUnavailable:
            raise  # phone links cannot be checked at all: refuse the whole accept, never call them "not in case"
        except link_types.LinkTargetError:
            refused.append(uid)
            continue
        if len(links) < MAX_LINKS:
            links.append({"target_type": "phone_record", "target_id": uid,
                          "source_anchor": {"agent_message_id": str(message.id)}})
    out = dossier_service.create_assessment(db, dossier_id=dossier.id, user=user, commit=False, data={
        "category": category, "content": content, "provenance_type": "ai_assisted",
        "agent_message_id": message.id, "supporting_links": links})
    over = max(0, len(cited) - len(refused) - len(links))
    out["cited_records"] = {"cited": len(cited), "linked": len(links), "not_in_case": len(refused),
                            "over_limit": over}
    notes = []
    if refused:
        notes.append("%d cited record%s %s not in this case and %s not linked." % (
            len(refused), "" if len(refused) == 1 else "s", "is" if len(refused) == 1 else "are",
            "was" if len(refused) == 1 else "were"))
    if over:
        notes.append("Only the first %d cited records are linked; %d more are cited in the text." % (MAX_LINKS, over))
    out["cited_records"]["sentence"] = " ".join(notes) or None
    return out
