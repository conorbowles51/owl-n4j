"""A chat answer from the case agent, added to a theory (link type ``agent_answer``, lx-theorybuild A, C).

An answer is a model reading. The link keeps it as one: its anchor says ``reading: model`` with the model that
wrote it, the thread and turn it came from, the answer's text as written (up to ``EXCERPT_LIMIT`` characters, with
``clipped`` saying so when longer) and every source it cites (``txn://``, ``doc://``, ``rec://`` and the other
schemes the agent writes). The theory page shows it under the model's name with those citations until a person
confirms what it says; it is never shown as the person's own reading.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select

EXCERPT_LIMIT = 4000
CITATIONS_LIMIT = 200
_CITE = re.compile(r"\b((?:txn|doc|rec|ent|evt|acct|party|thread|pa|sel)://[^\s)\]>\"']+)")


class AnswerLinkError(ValueError):
    pass


def citations_in(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(1).rstrip(".,;:") for m in _CITE.finditer(text or "")))


def answer_target(db, case_id, target_id: str) -> tuple[str, dict[str, Any]]:
    """(label, anchor) for an agent answer of this case, or AnswerLinkError."""
    from postgres.models.agent import AgentMessage, AgentThread
    try:
        mid = uuid.UUID(str(target_id))
        case = case_id if isinstance(case_id, uuid.UUID) else uuid.UUID(str(case_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AnswerLinkError(f"The agent answer {target_id} was not found in this case") from exc
    row = db.execute(select(AgentMessage, AgentThread.title).join(AgentThread, AgentThread.id == AgentMessage.thread_id)
                     .where(AgentMessage.id == mid, AgentThread.case_id == case)).first()
    if row is None:
        raise AnswerLinkError(f"The agent answer {target_id} was not found in this case")
    message, title = row
    if message.role != "assistant":
        raise AnswerLinkError("Only an answer from the agent can be added as an agent answer")
    text = message.content or ""
    cites = citations_in(text)
    anchor: dict[str, Any] = {
        "reading": "model",
        "model": message.model_id or message.model_provider or "the case agent",
        "thread_id": str(message.thread_id),
        "thread_title": title,
        "sequence_number": message.sequence_number,
        "answered_at": message.created_at.isoformat() if message.created_at else None,
        "excerpt": text[:EXCERPT_LIMIT],
        "citations": cites[:CITATIONS_LIMIT],
        "citation_count": len(cites),
    }
    if len(text) > EXCERPT_LIMIT:
        anchor["clipped"] = f"The answer is {len(text):,} characters; the first {EXCERPT_LIMIT:,} are kept here. Open it in the chat for all of it."
    if len(cites) > CITATIONS_LIMIT:
        anchor["citations_clipped"] = f"{CITATIONS_LIMIT} of {len(cites)} citations are kept here; the answer holds all of them."
    first = " ".join(text.split())[:140] or "(empty answer)"
    return f"Agent answer · {first}"[:512], anchor
