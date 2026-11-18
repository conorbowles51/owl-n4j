"""Deep investigation mode (lx-deepinvest C, D).

A normal agent run stops when the model believes it is done. A deep run first writes a coverage checklist from the
question and the case, works it item by item, keeps its findings in a run notebook outside the model's context,
is checked for completeness before it writes, and then writes a report in a fixed professional structure.

What is code and what is the model:
- the checklist (``build_plan``) is built from the question's domain and the case's own counts and phone labels,
  never from the model, and never from the content of any one case;
- the model marks items done with the units it covered (``deep_mark``); an item with a target count is done only
  when that many distinct units are named, so "every phone" means every phone;
- the gate (``open_items``, ``gate_message``) sends the run back to work while an item is open, a bounded number
  of times; what is still open then is stated in the report as not done, with the reason;
- the notebook (``notebook_add``) is the model's findings with citations; the model sees only counts and item
  titles while it works, and the writer receives the whole notebook once.

Decisions (16 Nov 2026; each says what would reverse it):
- D-a Phase 1 of the stored analyses runs as a system run through the existing request route
  (``services.phone_analysis.framework.request_run``), requested_by ``agent-deep-investigation``; the checklist
  says it was requested and whether it finished. Reverse if a person must approve a system run.
- D-b The gate allows ``MAX_GATES`` returns to work. Reverse if a measured run ends with open items that one more
  return would have closed.
- D-c Deep runs use the largest automatic window count the durable loop allows (32 windows of the usual budget).
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable

SCHEMA = "loupe.agent.deep/1"
MAX_GATES = 6
DEEP_WINDOWS = 32
DEEP_TOOLS = ("deep_checklist", "deep_mark", "deep_notebook_add", "deep_notebook_read")
NOTEBOOK_MAX_NOTES = 600
NOTE_MAX_CHARS = 700
# A live run cited one search-result record for 20 different facts and a fifth of its cited sentences were marked
# unsupported (agent runs of the citation check: 5 %). One record carries a few notes at most.
MAX_NOTES_PER_RECORD = 3

DOMAINS = ("phones", "money", "documents")

_ASK = re.compile(r"\b(deep(ly)?\s+(investigat\w*|report|dive|analysis)|detailed\s+(report|investigat\w*|analysis)|"
                  r"in[- ]depth\s+(report|investigat\w*|analysis)|full\s+(investigat\w*|report)|"
                  r"thorough(ly)?\s+(report|investigat\w*|analysis))", re.I)
_PHONE = re.compile(r"\b(phones?|handsets?|devices?|messages?|calls?|whatsapp|sms|imessage|extraction)\b", re.I)
_MONEY = re.compile(r"\b(money|payments?|transactions?|ledger|bank|accounts?|statements?|cash|transfers?|funds?|"
                    r"financ\w*)\b", re.I)
_DOCS = re.compile(r"\b(documents?|files?|contracts?|emails?|letters?|records?|filings?|reports? on the evidence)\b",
                   re.I)


def wants_deep(message: str) -> bool:
    """True when the person asks for a detailed or deep report or investigation in so many words."""
    return bool(_ASK.search(message or ""))


def domain_for(message: str, counts: dict[str, Any] | None = None) -> str:
    """The checklist the question calls for: the kind of material it names most; phones when it names several and
    the case holds phones, otherwise the kind the case holds."""
    text = message or ""
    score = {"phones": len(_PHONE.findall(text)), "money": len(_MONEY.findall(text)),
             "documents": len(_DOCS.findall(text))}
    best = max(score, key=lambda k: score[k])
    if score[best]:
        tied = [k for k in DOMAINS if score[k] == score[best]]
        return "phones" if "phones" in tied else tied[0]
    counts = counts or {}
    for kind, key in (("phones", "phones"), ("money", "ledger"), ("documents", "documents")):
        if counts.get(key):
            return kind
    return "phones"


# ---- the checklist -----------------------------------------------------------------------------------------------

def _item(id_, title, why, *, units=None, needs=()):
    """``units``: the distinct things the item covers (phone labels, windows); done needs each one named."""
    return {"id": id_, "title": title, "why": why, "status": "open", "reason": None,
            "target": list(units) if units else None, "covered": [], "needs": list(needs)}


MAX_DOC_UNITS = 60


def _phones_items(labels: list[str], docs: list[str]) -> list[dict]:
    n = len(labels)
    return [
        _item("incidents", "Dates and times of the incidents the case is about",
              "Read them from the case documents first; every window below is built from them."),
        _item("inventory", "Every phone: who it belongs to, what it holds, the period it covers, what is missing",
              "The reader needs the inventory before any reading of it.", units=labels),
        _item("attribution", "Who owns or uses each phone, with the evidence for each and how sure it is",
              "State the owner as stated, as shown by the contents and as the analyses grade it; say where they differ.",
              units=labels),
        _item("conversations", "Every conversation on every phone read to its end, by window and by phone",
              "Page by period and by phone until the end; a keyword search alone is not reading.", units=labels),
        _item("windows", "For each incident window and each phone: messages, calls, positions and gaps",
              "A gap or a missing position is stated as a finding, with where it was looked for.", units=labels),
        _item("network", "The contact network: who talks to whom, and the same person under different names or numbers",
              "Aliases and several numbers for one person change who the reader thinks was involved."),
        _item("client", "For the client named in the case setup: alibi positions in each incident window, and, for every "
              "other person the case ties to the incidents and every number of theirs, whether the client's phone holds "
              "any contact, call or message with them, and the reverse",
              "What the phones say for the client, and what they do not say, matters as much as what they say against. "
              "Check by number as well as by name, in both directions; an absence is stated with the numbers searched."),
        _item("deleted", "Deleted and recovered messages: who sent each, in which direction, and what remains",
              "A recovered copy on the sender's phone is the sent message, not a received one."),
        _item("analyses", "Stored analyses read; those not yet run were requested and read or the reason given",
              "A stored analysis that has not run is started, not reported as absent."),
        _item("documents", "Cross-checks of the phones against the documents: every document read in full",
              "Documents give times, places and names to hold the phones against. List them with get_evidence_files "
              "and read each with get_document_text; note what each gives, or that it gives nothing for this question.",
              units=docs or None),
        _item("money", "Cross-checks of the phones against the ledger",
              "A payment, a withdrawal or an account named in a message is held against the ledger."),
        _item("media", "Photos and files: when created, when received, where from",
              "Created and received are different events; the time zone the device recorded is not the place it was."),
        _item("chance", "Chance and decoy checks: busy places, recycled numbers, same first names, time zones",
              "A link that chance explains is stated as explained, not as a finding."),
        _item("flags", "Flagged communications, each graded by a stated rule with the reasons",
              "Say which rule was used, what it found, and what would lower the grade."),
    ] if n else [
        _item("inventory", "The case holds no phones: say so, and what was searched", "Nothing else can be reported."),
    ]


def _money_items() -> list[dict]:
    return [
        _item("scope", "The accounts, holders, periods and currencies the ledger covers, and what is missing",
              "Coverage first: a total over part of the period is not a total."),
        _item("incidents", "Dates and amounts the case documents give as the events in question",
              "Read them from the documents first."),
        _item("flows", "Money in and out per account and counterparty, over the whole period, by currency",
              "Totals come from the ledger tools, never from the model's own arithmetic."),
        _item("large", "Largest payments, cash, round sums and unusual timing, each read to the source page",
              "Every one cited to its statement row."),
        _item("parties", "Who each counterparty is, from the documents and the phones",
              "A name on a row is held against the other sources."),
        _item("patterns", "Repeated, split or circular payments and the gaps between them", "Stated with the rows."),
        _item("corrections", "Rows a person corrected and rows that could not be read cleanly",
              "Only corrected values are used; the original stays visible."),
        _item("documents", "Cross-checks of the money against the documents", "Invoices, contracts and letters."),
        _item("phones", "Cross-checks of the money against messages and calls", "A message about a payment, and its row."),
        _item("chance", "Explained items: ordinary payments that look unusual and why they are not", "Stated, with the reason."),
    ]


def _documents_items(docs: list[str]) -> list[dict]:
    return [
        _item("inventory", "Every document: kind, date, author, how far it was read", "Coverage first.", units=docs or None),
        _item("incidents", "Dates, places, people and amounts each document gives", "Read by document, in full."),
        _item("people", "Who is named, under which names, and who is the same person", "Aliases across documents."),
        _item("timeline", "What the documents say happened, in date order, each line cited", "One reconstruction."),
        _item("conflicts", "Where documents disagree with each other", "Stated with both sources."),
        _item("money", "Cross-checks against the ledger", "Amounts and dates held against rows."),
        _item("phones", "Cross-checks against the phones", "Times and places held against messages."),
        _item("chance", "Explained items and look-alikes", "A link chance explains is stated as explained."),
    ]


def unique_units(values: Iterable[Any]) -> list[str]:
    """Unit names in order, each once (case-insensitive) and none empty. Two files of one name (the same statement in
    two folders) are one unit: a note names the unit, and a target that holds a name twice can never be covered."""
    seen, out = set(), []
    for v in values:
        name = str(v or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def build_plan(domain: str, *, question: str, counts: dict[str, Any] | None = None,
               phone_labels: Iterable[str] = (), document_labels: Iterable[str] = ()) -> dict[str, Any]:
    """The run's checklist. Built from code, so a run cannot skip an item by not writing it down. ``document_labels``:
    the case's documents; each is a unit of the documents item when there are at most MAX_DOC_UNITS of them (a
    larger case is triaged, and the item says so)."""
    labels = unique_units(phone_labels)
    docs = unique_units(document_labels)
    docs = docs if len(docs) <= MAX_DOC_UNITS else []
    if domain == "phones":
        items = _phones_items(labels, docs)
    elif domain == "money":
        items = _money_items()
    elif domain == "documents":
        items = _documents_items(docs)
    else:
        raise ValueError("Unknown deep investigation domain %r" % domain)
    return {"schema": SCHEMA, "domain": domain, "question": question, "items": items, "notebook": [],
            "gates": 0, "analyses": [], "counts": {k: v for k, v in (counts or {}).items() if v is not None}}


def item_by_id(plan: dict, item_id: str) -> dict | None:
    return next((i for i in plan["items"] if i["id"] == item_id), None)


def is_closed(item: dict) -> bool:
    if item["status"] == "not_done":
        return bool(item.get("reason"))
    if item["status"] != "done":
        return False
    return not item["target"] or len(set(item["covered"])) >= len(set(item["target"]))


def open_items(plan: dict) -> list[dict]:
    return [i for i in plan["items"] if not is_closed(i)]


def progress(plan: dict) -> dict[str, Any]:
    """True numbers for the page: items closed, items open, and per item the units covered of the units needed."""
    items = []
    for i in plan["items"]:
        items.append({"id": i["id"], "title": i["title"], "status": "done" if is_closed(i) and i["status"] == "done"
                      else ("not_done" if is_closed(i) else i["status"]), "reason": i.get("reason"),
                      "covered": len(set(i["covered"])), "of": len(i["target"]) if i["target"] else None})
    closed = sum(1 for i in plan["items"] if is_closed(i))
    return {"schema": SCHEMA, "domain": plan["domain"], "total": len(plan["items"]), "closed": closed,
            "open": len(plan["items"]) - closed,
            "not_done": sum(1 for i in plan["items"] if i["status"] == "not_done" and is_closed(i)),
            "notes": len(plan["notebook"]), "items": items,
            "analyses": [{k: a.get(k) for k in ("approach", "status", "created")} for a in plan.get("analyses", [])]}


def _noted(plan: dict, item: dict, unit: str | None = None) -> bool:
    """A note under the item (naming the unit, when the item has units): the evidence that the work was done."""
    for n in plan["notebook"]:
        if n.get("item") == item["id"] and (unit is None or unit.lower() in (n["fact"] + " " + n["cite"]).lower()):
            return True
    return False


def mark(plan: dict, updates: list[dict]) -> dict[str, Any]:
    """Apply the model's marks. Returns what was applied and what was refused, in plain words. An item is done only
    with a note under it (for each unit, a note that names it): a finding, or an absence recorded as a note whose
    citation reads 'searched: <what was searched>'."""
    applied, refused = [], []
    for u in updates or []:
        item = item_by_id(plan, str(u.get("item") or ""))
        if item is None:
            refused.append({"item": u.get("item"), "why": "No such checklist item."})
            continue
        status = str(u.get("status") or "")
        units = [str(x).strip() for x in (u.get("units") or []) if str(x).strip()]
        if item["target"]:
            known = {t.lower(): t for t in item["target"]}
            for x in units:
                canon = known.get(x.lower())
                if canon and canon not in item["covered"] and _noted(plan, item, canon):
                    item["covered"].append(canon)
        if status == "done":
            if item["target"] and len(set(item["covered"])) < len(item["target"]):
                missing = [t for t in item["target"] if t not in item["covered"]]
                item["status"] = "in_progress"
                refused.append({"item": item["id"], "why": "Not yet done: no note under this item for %s. Read each, "
                                "then record what it showed with deep_notebook_add (item %s, naming it)." % (
                                    ", ".join(missing), item["id"])})
                continue
            if not item["target"] and not _noted(plan, item):
                item["status"] = "in_progress"
                refused.append({"item": item["id"], "why": "Not yet done: no note under this item. Record what the "
                                "work found with deep_notebook_add (item %s); an absence is a note whose citation reads "
                                "'searched: <what was searched>'." % item["id"]})
                continue
            item["status"], item["reason"] = "done", None
        elif status == "not_done":
            reason = str(u.get("reason") or "").strip()
            if not reason:
                refused.append({"item": item["id"], "why": "Not done needs the reason, in plain words."})
                continue
            item["status"], item["reason"] = "not_done", reason[:400]
        elif status == "in_progress":
            item["status"] = "in_progress"
        else:
            refused.append({"item": item["id"], "why": "Status must be done, not_done or in_progress."})
            continue
        applied.append(item["id"])
    return {"applied": applied, "refused": refused}


def notebook_add(plan: dict, notes: list[dict]) -> dict[str, Any]:
    """Findings with citations, kept outside the model's context. A note without a citation is refused: the report
    cites every claim."""
    added, refused = 0, []
    for n in notes or []:
        fact = str(n.get("fact") or "").strip()
        cite = str(n.get("cite") or "").strip()
        item = str(n.get("item") or "").strip()
        if not fact:
            continue
        if not cite:
            refused.append({"fact": fact[:80], "why": "No citation. Give the link the result carried."})
            continue
        if cite.startswith("rec://") and sum(1 for x in plan["notebook"] if x["cite"] == cite[:300]) >= MAX_NOTES_PER_RECORD:
            refused.append({"fact": fact[:80], "why": "That record already carries %d notes. A record shows one thing: "
                            "cite the link of the record this fact came from." % MAX_NOTES_PER_RECORD})
            continue
        if len(plan["notebook"]) >= NOTEBOOK_MAX_NOTES:
            refused.append({"fact": fact[:80], "why": "The notebook holds %d notes." % NOTEBOOK_MAX_NOTES})
            continue
        plan["notebook"].append({"n": len(plan["notebook"]) + 1, "item": item or None, "fact": fact[:NOTE_MAX_CHARS],
                                 "cite": cite[:300]})
        added += 1
    return {"added": added, "total": len(plan["notebook"]), "refused": refused}


def notebook_read(plan: dict, item: str | None = None, offset: int = 0, limit: int = 40) -> dict[str, Any]:
    rows = [n for n in plan["notebook"] if not item or n.get("item") == item]
    page = rows[offset:offset + limit]
    nxt = offset + limit if offset + limit < len(rows) else None
    return {"total": len(rows), "returned": len(page), "next_offset": nxt, "notes": page}


def notebook_block(plan: dict) -> str:
    """The whole notebook, once, for the writer (the final answer's own prompt)."""
    if not plan["notebook"]:
        return "The run notebook is empty: say that no findings were noted."
    lines = ["Run notebook: the findings of this run, each with its citation. Use them; cite each claim with its link."]
    for n in plan["notebook"]:
        lines.append("- [%s] %s (%s)" % (n.get("item") or "general", n["fact"], n["cite"]))
    return "\n".join(lines)


# An absence the run found and noted ("no call or message between A and B, numbers searched ...") was dropped
# from the report in deep runs 5 and 6 of the demo case (F05). The writer is told to state each one as a finding.
_ABSENCE = re.compile(r"\b(no (?:direct )?(?:contact|calls?|messages?|communications?|record of contact)|never "
                      r"(?:called|messaged|contacted|spoke)|did not (?:call|message|contact)|nothing between|"
                      r"not (?:once )?in contact)\b", re.I)


def absence_block(plan: dict) -> str:
    """The noted absences of contact the report must state as findings, each with what was searched."""
    notes = [n for n in plan.get("notebook") or [] if _ABSENCE.search(n.get("fact") or "")]
    if not notes:
        return ""
    return ("These absences of contact were found and noted. State each one as a finding in the report (in the "
            "client's section and the contact network), with the numbers and phones searched and its citation, in "
            "plain words such as 'no call or message between':\n"
            + "\n".join("- %s (%s)" % (n["fact"], n["cite"]) for n in notes))


# ---- the gate ----------------------------------------------------------------------------------------------------

def gate_message(plan: dict) -> str | None:
    """The note that sends the run back to work, or None when it may write (every item closed, or the gate spent)."""
    left = open_items(plan)
    if not left or plan["gates"] >= MAX_GATES:
        return None
    plan["gates"] += 1
    rows = []
    for i in left:
        need = ""
        if i["target"]:
            missing = [t for t in i["target"] if t not in i["covered"]]
            need = " Still to cover: %s." % ", ".join(missing) if missing else ""
        rows.append("- %s: %s.%s" % (i["id"], i["title"], need))
    return ("Completeness check of the deep investigation, not a new instruction from the person (return %d of %d). "
            "These checklist items are still open:\n%s\nWork them now with the case tools and mark each with deep_mark "
            "(done, with the units covered), keeping findings with deep_notebook_add. An item you cannot do is marked "
            "not_done with the reason. Do not write the report while an item is open." % (plan["gates"], MAX_GATES,
                                                                                         "\n".join(rows)))


def not_done_block(plan: dict) -> str:
    """What the report must say about items not done, in the writer's rules."""
    items = [i for i in plan["items"] if not (is_closed(i) and i["status"] == "done")]
    if not items:
        return ""
    rows = []
    for i in items:
        why = i.get("reason") or "the run ended before this was worked"
        if i["target"] and i["covered"]:
            why += " (covered %d of %d)" % (len(set(i["covered"])), len(i["target"]))
        rows.append("- %s: %s" % (i["title"], why))
    return ("Under 'Limits and next steps' state each of these as not done, with its reason, in plain words:\n"
            + "\n".join(rows))


# ---- prompts (no case-specific wording: a test greps this file for the demo case's names) ---------------------------

METHOD = {
    "phones": ("How to read the phones: phone_coverage and get_person_phones for the inventory and owners; "
               "read_scope_with_model for each phone and each incident window (a model reads every message and call in "
               "chunks and returns the relevant ones with cites; page on with next_offset, and treat its output as a "
               "reading to check against phone_record before citing), or phone_messages for each phone on its own "
               "(phones=[its label], no search words), paging (offset) until has_more is false, noting what each "
               "page shows before the next; then each incident window again; "
               "get_day_activity, get_together_apart and phone_places for positions and gaps in each window; "
               "get_analysis_results for each stored analysis kind; get_money_signal_matches and "
               "get_payment_conversation for the ledger; search_documents and get_document_text for the incident "
               "dates and the documents; get_near_identical_pictures and phone_record for photos and files; "
               "get_identity_suggestions for the same person under several numbers."),
    "money": ("How to read the money: get_financial_coverage first; get_financial_transactions and "
              "analyze_financial_transactions for flows (page until has_more is false); get_money_between, "
              "find_connected_payments, get_transfer_pairs and get_payment_other_legs for counterparties and "
              "chains; get_statement_continuity for gaps; get_account_mentions and search_documents for who and "
              "why; phone_messages for what was said about a payment."),
    "documents": ("How to read the documents: get_evidence_files for the inventory and how far each was read; "
                  "search_documents, search_exact_words and get_document_text (or read_scope_with_model with the file's id) to read each one; search_case for "
                  "names and numbers across all kinds; check_statements for what a document says against the rest."),
}


def render_block(plan: dict) -> str:
    """The working method the agent sees for the whole run."""
    lines = [
        "DEEP INVESTIGATION. The person asked for a detailed report. Work it as an investigator would, and do not "
        "stop because you think you have enough.",
        "You have a coverage checklist (deep_checklist shows it with true counts). Work it item by item. Read by "
        "window and by phone and page to the end; never rely on keyword guesses alone, and never conclude 'no link' "
        "from a search that found nothing: say what was searched.",
        "Start with the case documents for the incident dates and times, and the case setup for who the client is. "
        "Use every relevant tool and stored analysis. A stored analysis that has not run was requested for you; "
        "read it when it has finished and say so when it has not.",
        "After each reading that gives facts the report will use, record them with deep_notebook_add, each with its "
        "citation link, which is the link of the very record or page the fact came from (never one link reused for "
        "facts it does not show). Notes are kept outside your context, so note freely and do not read a result again. Mark an "
        "item with deep_mark when it is covered (done, with the units covered) or cannot be done (not_done, with the "
        "reason). These calls do not count as tool steps.",
        "Hold every link against what chance explains: a busy place, a number that changed hands, the same first "
        "name, a photo's creation time against its arrival, the time zone the device recorded against where the "
        "person was. A link that chance explains is reported as explained, not as a finding.",
        "A message recovered from the sender's phone is a message that person sent; the copy on the other phone may "
        "be absent. Give the direction from the sender, never from which phone it was found on.",
        "Dates and times of events at night are given in the local time with the zone named, with the date the "
        "people lived it. Phone rows carry local_day, time and time_zone; every other UTC time a tool gives has "
        "a <name>_local beside it in the case's zone: use those, and never convert a time yourself. Where a tool "
        "gives only a UTC instant, say UTC beside it and do not use its date as the local date.",
        "Hold every name against its history: a name saved on one phone for a number, and the dates of the calls "
        "and messages under that name, show whether the number had another holder earlier. A person who shares a "
        "first name with another is a different person until a record joins them.",
        "Your readings are your readings: label them as such until a person confirms.",
        "Write the report as your final answer, in markdown. Do not build report, table or other artifacts: the "
        "finished answer is saved as a report the person exports to PDF.",
        METHOD.get(plan["domain"], ""),
        "Checklist for this question (%s): %s" % (plan["domain"], "; ".join(i["id"] for i in plan["items"])),
    ]
    return "\n".join(lines)


def final_rules(plan: dict | None = None) -> str:
    """The structure of the report. The final answer is written under its own prompt, which does not see the plan."""
    base = (
        "This is a deep investigation report a firm could give its client. Use these headed sections, in this order: "
        "1. Summary for the client (what matters to the client, first: what helps and what harms, and how sure each is). "
        "2. Inventory (each phone or account or document: what it is and what it holds, with its limits). "
        "3. Attribution (who owns each, the evidence, and the confidence in words). "
        "4. Contact network (who deals with whom, and the same person under several names or numbers). "
        "5. One reconstruction for each incident window (what each source shows, in time order, with positions and "
        "gaps). "
        "6. Flagged communications, each graded by a stated rule with the reasons. "
        "7. Cross-checks against the documents and the ledger. "
        "8. Explained items and look-alikes (what chance explains). "
        "9. What this means for the client. "
        "10. Limits and next steps (what was not done and why, what a person must confirm). "
        "Rules: write the contents list from the sections you write, and each heading once. Every sentence that "
        "states a fact carries its citation link. Every sentence names who and which phone; never leave a name out "
        "of a sentence. Say 'no link found' only with what was searched. Model readings are labelled as the "
        "assistant's reading until a person confirms them. Give times in local time with the zone, and say UTC "
        "where UTC is meant.")
    return base + (("\n" + not_done_block(plan)) if plan else "")


def checkpoint_state(plan: dict | None) -> dict | None:
    return deepcopy(plan) if plan else None


def mark_unsupported_glyphs(text: str) -> str:
    """Characters the export fonts lack (emoji in a quoted message) would fail the PDF and Word export. Each is
    written as its code point in brackets, so the reader sees that a symbol was there and nothing is dropped."""
    import unicodedata
    from services.agent.export_documents import _export_glyphs
    supported = _export_glyphs()
    return "".join(
        c if (c.isspace() or unicodedata.category(c) in {"Cc", "Cf"} or ord(c) in supported) else "[U+%04X]" % ord(c)
        for c in text)


def report_artifact(answer: str, plan: dict) -> dict | None:
    """The finished answer as a report artifact, so it exports through the existing PDF and Word path. Sections are
    the answer's own headings; text before the first heading is the opening section. None when there is no text."""
    import re
    text = mark_unsupported_glyphs((answer or "").strip())
    if not text:
        return None
    from services.agent.tools import _artifact
    title = "Deep investigation report"
    first = re.match(r"^\s{0,3}#\s+(.+?)\s*#*\s*$", text, re.M)
    if first:
        title = first.group(1).strip()[:160]
    sections: list[dict] = []
    parts = re.split(r"^(?=\s{0,3}#{1,4}\s)", text, flags=re.M)
    for part in parts:
        if not part.strip():
            continue
        head = re.match(r"^\s{0,3}(#{1,4})\s+(.+?)\s*#*\s*$", part, re.M)
        if head and part.lstrip().startswith("#"):
            level, heading = len(head.group(1)), head.group(2).strip()[:160]
            body = part[head.end():].strip() or "No text."
        else:
            level, heading, body = 2, "Summary", part.strip()
        if level == 1 and not sections and not body.strip("# "):
            continue
        sections.append({"id": "section-%d" % (len(sections) + 1), "heading": heading, "content": body,
                         "level": max(1, min(level, 6)), "embeds": []})
    if not sections:
        return None
    return _artifact("report", title, {
        "title": title, "purpose": "A deep investigation of the case, written for the person who asked.",
        "audience": "", "scope": plan.get("question", "")[:1500],
        "included_items": [i["title"] for i in plan["items"]][:40], "sections": sections,
        "embedded_artifacts": [], "open_questions": []},
        {"section_count": len(sections), "embedded_artifact_count": 0, "source_result_ids": [],
         "revision_note": "", "status": "draft", "origin": "deep_investigation",
         "checklist": progress(plan)})
