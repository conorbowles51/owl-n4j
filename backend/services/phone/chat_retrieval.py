"""Chat reaches phone text by lexical retrieval (docs/cellebrite/02 section 9.8; 02-U14).

Phone text is never embedded while the only embedding provider is a third party and the case has no
``allow_phone_external_processing`` decision (plan standing decision 8). Chat instead runs the folded search over the
case's thread documents (02 section 9.7, ``source_type = 'phone_text'``) for the question's terms and adds up to 8
message windows as chunks: consecutive lines of one thread up to 3,500 characters around the lines that match,
read in full (no opaque labels; Neil 2026-11-01), each line citing its record (``rec://``). The windows carry the
engine's chunk metadata keys plus ``source_kind = "phone_text"``, ``extraction_id``, ``first_record_uid`` and
``last_record_uid``. Every query names the case.
"""
from __future__ import annotations

import re

from sqlalchemy import text

from services.phone import fold as F

MAX_WINDOWS = 8
WINDOW_CHARS = 3500
MAX_TERMS = 8
CANDIDATE_DOCS = 40
STOP = frozenset("""a about above after again against all also am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further had has have having he
her here hers herself him himself his how i if in into is it its itself just me more most my myself no nor not now of
off on once only or other our ours ourselves out over own same she should so some such than that the their theirs
them themselves then there these they this those through to too under until up very was we were what when where
which while who whom why will with would you your yours yourself yourselves tell show find list give say said says
message messages phone phones text texts sent send call calls called anyone someone something did does any ever
please know about mention mentioned""".split())
WORD = re.compile(r"[^\W_]{3,}", re.UNICODE)
PHRASE = re.compile(r'"([^"]{3,80})"')
DIGITS = re.compile(r"\+?\d[\d\s().-]{5,}\d")


def terms(question: str) -> list:
    """The question's search terms, folded: quoted phrases, numbers (digits only), then words of 3 or more letters
    that are not common words, longest first; at most 8."""
    out = []
    for p in PHRASE.findall(question or ""):
        out.append(F.fold(p))
    rest = PHRASE.sub(" ", question or "")
    for d in DIGITS.findall(rest):
        digits = re.sub(r"\D", "", d)
        if len(digits) >= 4:
            out.append(digits)
    rest = DIGITS.sub(" ", rest)
    words = [F.fold(w) for w in WORD.findall(rest)]
    words = [w for w in words if w and w not in STOP]
    out.extend(sorted(set(words), key=lambda w: (-len(w), w)))
    seen, uniq = set(), []
    for t in out:
        t = (t or "").strip()
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq[:MAX_TERMS]


def _like(q):
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _line_bounds(content: str):
    starts, pos = [], 0
    for line in content.split("\n"):
        starts.append((pos, pos + len(line)))
        pos += len(line) + 1
    return starts


def _matched_lines(content, folded, fold_map, ts, bounds):
    """``{line index: set(terms)}`` for every line holding a term (folded match mapped to the original)."""
    import bisect
    starts = [b[0] for b in bounds]
    hits = {}
    for t in ts:
        at = folded.find(t) if folded is not None else content.casefold().find(t)
        while at >= 0:
            if folded is not None:
                s, _ = F.original_span(fold_map, at, at + len(t))
            else:
                s = at
            i = max(0, bisect.bisect_right(starts, s) - 1)
            hits.setdefault(i, set()).add(t)
            at = (folded.find(t, at + len(t)) if folded is not None else content.casefold().find(t, at + len(t)))
    return hits


def _window(bounds, centre, limit=WINDOW_CHARS):
    """Line range [lo, hi] around ``centre`` growing alternately forward and back while under ``limit``."""
    lo = hi = centre
    size = bounds[centre][1] - bounds[centre][0]
    grew = True
    while grew:
        grew = False
        for step in (1, -1):
            j = hi + 1 if step == 1 else lo - 1
            if 0 <= j < len(bounds):
                add = bounds[j][1] - bounds[j][0] + 1
                if size + add <= limit:
                    size += add
                    if step == 1:
                        hi = j
                    else:
                        lo = j
                    grew = True
    return lo, hi


def windows(conn, case_id, question, *, max_windows=MAX_WINDOWS) -> list:
    """Chunks shaped as the vector search returns them (``id``, ``text``, ``metadata``, ``distance``), best first."""
    ts = terms(question)
    if not ts:
        return []
    from services.search import document_folds
    params = {"c": str(case_id), "v": document_folds.FOLD_VERSION}
    conds = []
    for i, t in enumerate(ts):
        params["l%d" % i], params["q%d" % i] = _like(t), t
        conds.append("((x.evidence_file_id IS NOT NULL AND x.content_folded LIKE :l%d) OR (x.evidence_file_id IS NULL "
                     "AND position(:q%d in lower(t.content)) > 0))" % (i, i))
    score = " + ".join("(%s)::int" % c for c in conds)
    rows = conn.execute(text(
        "SELECT f.id, f.original_filename, f.metadata, t.content, t.source_locations, x.content_folded, x.fold_map, "
        "%s AS score FROM evidence_files f JOIN evidence_document_texts t ON t.evidence_file_id = f.id "
        "JOIN phone_extractions e ON e.id::text = f.metadata ->> 'phone_extraction_id' AND e.case_id = f.case_id "
        "AND e.standing = 'active' LEFT JOIN evidence_text_folds x ON x.evidence_file_id = f.id AND "
        "x.content_sha256 IS NOT DISTINCT FROM t.content_sha256 AND x.fold_version = :v WHERE f.case_id = :c AND "
        "f.source_type = 'phone_text' AND (%s) ORDER BY 8 DESC, f.original_filename, f.id LIMIT %d"
        % (score, " OR ".join(conds), CANDIDATE_DOCS)), params).fetchall()
    found = []
    for r in rows:
        bounds = _line_bounds(r.content)
        hits = _matched_lines(r.content, r.content_folded, r.fold_map, ts, bounds)
        for i, matched in hits.items():
            found.append((len(matched), r, bounds, i, matched))
    found.sort(key=lambda x: (-x[0], x[1].original_filename, x[3]))
    out, taken = [], {}
    for n, r, bounds, i, matched in found:
        spans = taken.setdefault(r.id, [])
        if any(lo <= i <= hi for lo, hi in spans):
            continue
        lo, hi = _window(bounds, i)
        spans.append((lo, hi))
        s, e = bounds[lo][0], bounds[hi][1]
        locs = [l for l in (r.source_locations or []) if l.get("kind") == "phone_record" and
                l.get("field_path") == "Body" and s <= int(l.get("start_char", -1)) < e]
        locs.sort(key=lambda l: int(l["start_char"]))
        hit_loc = next((l for l in locs if bounds[i][0] <= int(l["start_char"]) <= bounds[i][1]), locs[0] if locs else {})
        meta = r.metadata or {}
        lines = []
        for l in locs:
            body = r.content[int(l["start_char"]):int(l["end_char"])]
            lines.append("%s [rec://%s]" % (body, l["record_uid"]))
        text_ = "\n".join(lines) if lines else r.content[s:e]
        out.append({
            "id": "phone:%s:%d-%d" % (r.id, s, e), "text": text_,
            # more question terms on the line: nearer; the vector search's distances run 0 (same) to 2
            "distance": round(1.0 - 0.6 * n / len(ts), 4),
            "metadata": {"case_id": str(case_id), "doc_id": str(r.id), "doc_name": r.original_filename,
                         "filename": r.original_filename, "evidence_file_id": str(r.id),
                         "ingestion_state": "active", "start_char": s, "end_char": e, "source_kind": "phone_text",
                         "extraction_id": meta.get("phone_extraction_id"),
                         "first_record_uid": locs[0]["record_uid"] if locs else None,
                         "last_record_uid": locs[-1]["record_uid"] if locs else None,
                         "record_uid": hit_loc.get("record_uid"),
                         "url": "rec://%s" % hit_loc["record_uid"] if hit_loc.get("record_uid") else None,
                         "matched_terms": sorted(matched)},
        })
        if len(out) >= max_windows:
            break
    return out
