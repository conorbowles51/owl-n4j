"""Who contacted whom, for chat: the same count the agent's contact tool gives, with Loupe's identity suggestions.

Chat found phone text by words only, so "Did Mateo Ruiz ever call or message Desmond Okafor?" was answered "Yes" or "No"
from whatever messages held the two names, never from the calls and messages between the two people's phones. When the
question names two or more people of the case, this adds one passage per pair: the calls, messages and emails between
them, counted through the identities a person linked and, when no person has, through the identity suggestions and owner
records, each stated with its basis and strength (lx-agentquick D10 for chat). Nothing is linked or stored.
"""
from __future__ import annotations

import logging
from itertools import combinations

from sqlalchemy import text

log = logging.getLogger(__name__)
MAX_PEOPLE = 4  # six pairs at most


def people_named(conn, case_id, question) -> list:
    """The people (dossiers) of the case whose whole name the question holds, folded; longest names first."""
    from services.phone import fold as F
    q = " %s " % F.fold(question or "")
    found = []
    for r in conn.execute(text("SELECT id::text AS id, display_name FROM case_profiles WHERE case_id = :c AND "
                               "archived_at IS NULL"), {"c": str(case_id)}):
        name = F.fold(r.display_name or "").strip()
        if len(name) >= 5 and " " in name and " %s " % name in q:
            found.append((r.id, r.display_name))
    found.sort(key=lambda x: -len(x[1] or ""))
    # a name inside a longer named person's name is that person
    return found[:MAX_PEOPLE]


def _line(label, n_calls, n_msgs, n_mail):
    return "%d call%s, %d message%s, %d email%s" % (n_calls, "" if n_calls == 1 else "s", n_msgs,
                                                    "" if n_msgs == 1 else "s", n_mail, "" if n_mail == 1 else "s")


def passages(conn, case_id, question) -> list:
    """One chunk per pair of named people, in the shape the other retrieval stages return; ``[]`` when the question
    names fewer than two people or a pair cannot be read."""
    from services.agent import phone_cross_tools as PC
    people = people_named(conn, case_id, question)
    out = []
    for (ida, na), (idb, nb) in combinations(people, 2):
        try:
            r = PC.contact_and_money_between(conn, case_id, person_a=ida, person_b=idb, suggestions=True)
        except Exception:  # noqa: BLE001 - the answer goes on without this passage
            log.exception("contact between %s and %s could not be read", na, nb)
            continue
        if not isinstance(r, dict) or r.get("error"):
            continue
        from services.phone import link_edges
        c = r.get("communication") or {}
        via = r.get("communication_through_suggested")
        pairs = r.get("suggested_pairs") or []
        if via:
            n = {k: int(via.get(k) or 0) for k in ("calls", "messages", "emails")}
        else:
            n = {k: link_edges.comm_total(c, k) if c else 0 for k in ("calls", "messages", "emails")}
        counted = _line("", n["calls"], n["messages"], n["emails"])
        basis = (" counted through identities that no person has linked to them (%s)" % via["basis"]) if via else ""
        body = "%s and %s: %s between them%s." % (na, nb, counted, basis)
        if not sum(n.values()):
            nums_a = sorted({str(p["a"]) for p in pairs})
            nums_b = sorted({str(p["b"]) for p in pairs})
            body += (" So the answer is no: no call, message or email is recorded between %s%s and %s%s. A contact saved "
                     "on one phone under a similar name or nickname, at any other number, is not %s or %s unless an "
                     "identity suggestion or a person's link ties that number to them; if you mention such a contact, "
                     "say it is at a different number and not established to be them." % (
                         na, " (%s)" % ", ".join(nums_a) if nums_a else "", nb,
                         " (%s)" % ", ".join(nums_b) if nums_b else "", na, nb))
        elif via:
            body += " Say so with the count; do not answer from the absence of a person's link."
        body += "\n" + str(r.get("label_line") or "")
        out.append({
            "id": "phone-contact:%s:%s" % (ida, idb), "text": body, "distance": 0.0,
            "metadata": {"case_id": str(case_id), "doc_id": "phone-contact:%s:%s" % (ida, idb),
                         "doc_name": "Phone contact between %s and %s" % (na, nb),
                         "filename": "Phone contact between %s and %s" % (na, nb),
                         "ingestion_state": "active", "source_kind": "phone_contact_count",
                         "no_cite": True}})  # a count has no file: no doc:// link to nothing
    return out
