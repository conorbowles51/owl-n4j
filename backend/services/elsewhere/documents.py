"""The Documents part: case documents (not phone text, not the statements the ledger was built from) that name
the subject's check numbers, account endings, amounts, people, firms or places.

A copy of a statement the ledger was built from (the same text) is left out too. Text is matched on the folded copy Search uses (``services.search.document_folds``), else as typed. Copies of the
same file (the same text) are one item that says how many copies there are.

Rules: a document that gives a check number of the subject and, beside it (within ``NEAR`` characters), the
amount the subject or the ledger gives for that check **agrees**; the check number beside another amount and not
that one **disagrees**; a document that names the subject's people, firms, places, account endings or amounts
without that is a **possible match**.
"""
from __future__ import annotations

import re

from sqlalchemy import text

from services.elsewhere import words as W
from services.phone import fold as F
from services.search import document_folds

NEAR = 160
MAX_FILES = 25
PER_PERSON = 4
AMOUNT_RE = re.compile(r"\$?\s?\d{1,3}(?:,\d{3})*\.\d{2}|\$\s?\d{1,3}(?:,\d{3})+")

DOC_FROM = ("FROM evidence_document_texts t JOIN evidence_files f ON f.id = t.evidence_file_id "
            "LEFT JOIN evidence_text_folds x ON x.evidence_file_id = t.evidence_file_id AND x.content_sha256 = "
            "t.content_sha256 AND x.fold_version = :v "
            "WHERE f.case_id = CAST(:c AS uuid) AND f.deleted_at IS NULL AND f.source_type IS DISTINCT FROM "
            "'phone_text' AND t.content IS NOT NULL AND NOT EXISTS (SELECT 1 FROM financial_source_documents d JOIN "
            "evidence_document_texts dt ON dt.evidence_file_id = d.evidence_file_id WHERE d.case_id = f.case_id AND "
            "d.status = 'admitted' AND (d.evidence_file_id = f.id OR dt.content_sha256 = t.content_sha256)) ")


def _like(q):
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _terms(subject, ledger_amounts):
    """``[(kind, shown, needle)]``: what is looked for, each with the words used to say it was found."""
    out = []
    for ref in subject.references:
        out.append(("reference", "check %s" % ref if ref.isdigit() else ref, ref))
    for end in subject.accounts:
        out.append(("account", "account ending %s" % end[-4:], end[-4:]))
    for minor, cur in subject.amounts:
        for form in W.money_forms(minor):
            out.append(("amount", W.money_text(minor, cur), form))
    for n in subject.names():
        toks = W.name_tokens(n)
        if W.strong_name(n) or (toks and len(toks[0]) >= 4):
            out.append(("person", " ".join(toks).title() if not W.strong_name(n) else n, " ".join(toks)))
    for t in subject.terms:
        out.append(("name", t, " ".join(W.name_tokens(t))))
    return out


def _find(conn, case_id, needle):
    fq = F.fold(needle)
    if not fq:
        return []
    return conn.execute(text(
        "SELECT f.id::text AS id, f.original_filename, t.content, t.content_sha256, t.source_locations, "
        "x.content_folded " + DOC_FROM + "AND ((x.evidence_file_id IS NOT NULL AND x.content_folded LIKE :like) OR "
        "(x.evidence_file_id IS NULL AND position(:q in lower(t.content)) > 0)) ORDER BY lower(f.original_filename), "
        "f.id LIMIT 200"), {"c": str(case_id), "v": document_folds.FOLD_VERSION, "like": _like(fq),
                            "q": needle.lower()}).fetchall()


def _page(locations, at):
    from services.search.search import _page as page_of
    return page_of(locations, at)


def _quote(content, at, length):
    s, e = max(0, at - 60), min(len(content), at + length + 60)
    return ("…" if s else "") + " ".join(content[s:e].split()) + ("…" if e < len(content) else "")


def _ref_positions(content, ref):
    if ref.isdigit():
        return [m.start(1) for m in re.finditer(r"(?<![0-9])(%s)(?![0-9])" % re.escape(ref), content)]
    return [m.start() for m in re.finditer(re.escape(ref), content, re.I)]


def _amounts_near(content, at):
    """Amounts within ``NEAR`` characters of ``at``; the window is widened to whole words, so an amount on its edge
    is read whole ("$2,460.00", never "460.00")."""
    s, e = max(0, at - NEAR), min(len(content), at + NEAR)
    while s > 0 and not content[s - 1].isspace():
        s -= 1
    while e < len(content) and not content[e].isspace():
        e += 1
    win = content[s:e]
    out = set()
    for m in AMOUNT_RE.finditer(win):
        if m.start() and (win[m.start() - 1].isdigit() or win[m.start() - 1] in ",."):
            continue
        out.add(int(round(float(re.sub(r"[^\d.]", "", m.group())) * 100)))
    for m in re.finditer(r"(?<![\d.,])(\d{2,7}\.\d{2})(?![\d])", win):
        out.add(int(round(float(m.group(1)) * 100)))
    return out


def part(conn, case_id, subject, zone, ledger_amounts=None) -> dict:
    """``ledger_amounts``: ``{reference: minor}`` the ledger gives, used when the subject states no amount."""
    terms = _terms(subject, ledger_amounts or {})
    files = {}
    for kind, shown, needle in terms:
        for r in _find(conn, case_id, needle):
            content = r.content or ""
            key = r.content_sha256 or r.id
            f = files.setdefault(key, {"row": r, "copies": set(), "hits": [], "refs": {}})
            f["copies"].add(r.id)
            low = content.lower()
            at = low.find(needle.lower())
            if kind == "reference":
                pos = _ref_positions(content, needle)
                if not pos:
                    continue
                f["refs"][needle] = pos
                at = pos[0]
            elif kind in ("name", "person"):
                at = F.fold(content).find(F.fold(needle)) if at < 0 else at
            f["hits"].append((kind, shown, needle, max(at, 0)))
    items, per_person = [], {}
    anchor = subject.amounts[0][0] if len(subject.amounts) == 1 else None
    for key, f in files.items():
        if not f["hits"]:
            continue
        r = f["row"]
        content = r.content or ""
        rel, reason, at_hit, matched = W.POSSIBLE, None, f["hits"][0], {h[0] for h in f["hits"]}
        for ref, pos in f["refs"].items():
            want = anchor if anchor is not None else (ledger_amounts or {}).get(ref)
            if want is None:
                continue
            near = set()
            for p in pos:
                near |= _amounts_near(content, p)
            hit = next(h for h in f["hits"] if h[2] == ref)
            if want in near:
                rel, at_hit = W.AGREES, hit
                reason = "Gives check %s with %s beside it, the amount %s gives." % (
                    ref, W.money_text(want), "this statement" if anchor is not None else "the ledger")
                matched.add("amount")
                break
            if near:
                rel, at_hit = W.DISAGREES, hit
                reason = "Gives check %s beside %s, not %s as %s gives." % (
                    ref, W.join_words([W.money_text(m) for m in sorted(near)]), W.money_text(want),
                    "this statement" if anchor is not None else "the ledger")
        shown = W.join_words(list(dict.fromkeys(h[1] for h in f["hits"])))
        if reason is None:
            reason = "Names %s; nothing ties this file to this %s by number and amount." % (shown, subject.kind)
        page = _page(r.source_locations, at_hit[3])
        copies = len(f["copies"])
        name = r.original_filename or "A document"
        cite = {"kind": "document", "id": r.id, "evidence_file_id": r.id, "href": "doc://%s%s" % (
                r.id, "/%d" % page if page else ""), "label": name + (" p.%d" % page if page else ""), "page": page,
                "quote": _quote(content, at_hit[3], len(at_hit[2]))}
        if rel == W.POSSIBLE and matched == {"person"}:
            # a file that only names the people: one line per person, as "Nell is named in 2 files"
            for h in f["hits"]:
                per_person.setdefault(h[1], []).append(dict(cite, quote=_quote(content, h[3], len(h[2]))))
            continue
        textline = "%s names %s%s." % (name, shown, " (%d copies of the same file)" % copies if copies > 1 else "")
        items.append(W.item(rel, textline, reason, cite, matched, copies=sorted(f["copies"])))
    for person, cites in per_person.items():
        cites = sorted(cites, key=lambda c: c["label"].lower())
        names = [c["label"].split(" p.")[0] for c in cites]
        shown_names = W.join_words(names[:PER_PERSON] + (["%d more" % (len(names) - PER_PERSON)]
                                                         if len(names) > PER_PERSON else []))
        items.append(W.item(W.POSSIBLE, "%s is named in %s: %s." % (person, W.plural(len(cites), "file"),
                                                                   shown_names),
                            "Same name; nothing ties these files to this %s by number or amount." % subject.kind,
                            cites[0], ["name"], also=cites[1:], _rank=1))
    items = W.sort_items(items)
    more = max(0, len(items) - MAX_FILES)
    items = items[:MAX_FILES]
    if more:
        items.append(W.item(W.POSSIBLE, "%s more documents name these too." % "{:,}".format(more),
                            "Only the first %d are listed here; Search lists them all." % MAX_FILES,
                            {"kind": "search", "screen": "search"}, []))
    searched = ("Searched every document in the case for %s. Bank statements the ledger was built from are read "
                "under Financial." % W.join_words(list(dict.fromkeys(t[1] for t in terms)))) if terms else (
        "Nothing to search documents for: no check number, account, amount, name, firm or place was given.")
    if not items:
        items.append(W.item(W.NOTHING, "No document names %s." % W.join_words(list(dict.fromkeys(
            t[1] for t in terms))) if terms else "No document searched.", searched, None))
    return {"searched": searched, "items": items}
