"""Search every phone (Phones screen 2, lx-phonesearch): one search across every part of every phone in scope.

``phone_search`` returns, for one query and the phone scope (phones, period):

- ``kinds``: each kind of record with its exact total and its exact count on each phone in scope (``by_phone``);
  messages, calls and emails count as Conversations counts them (copies collapsed, S-4), every other record once
  per top-level record (a contact found by its name and its number is one contact);
- ``groups``: the first hits of each kind with the matched text, newest last in time order, ``next_cursor`` when there
  are more (``kind_page`` pages the rest, 200 at most);
- ``saved_differently``: a person the query finds whom the phones save under different names (from the phones'
  contact records), with the phone that is their own;
- ``next_steps``: ranked steps computed from this result (COMMON rule 4);
- ``limits`` (phones still being read: the result is not presented as whole) and ``not_searched``.

Hidden values (passwords, cookies, typed words) are compared inside the backend on their whole value and come back
masked (search.records_items). Deleted items are searched like any other and say so.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

from services.phone import fold as F
from services.phone import streams
from services.phone import time_display as T
from services.search import search as S

FIRST = 5
MAX_PAGE = 200

# kinds of record, in the order the screen lists them; each other record kind is classed by its top-level record type
COMM = {"messages": ("message", "chat_activity"), "calls": ("call", "voicemail"), "emails": ("email",)}
RECORD_KINDS = {
    "contacts": ("Contact",),
    "web": ("VisitedPage", "SearchedItem", "WebBookmark", "Cookie"),
    "typed_words": ("DictionaryWord", "Autofill"),
    "accounts": ("UserAccount", "Password", "CreditCard", "SIMData", "MobileCard", "User"),
    "places": ("Location", "Journey", "CellTower", "WirelessNetwork"),
    "files_records": ("FileDownload", "FileUpload", "Recording"),
}
KINDS = (
    ("messages", "Messages"), ("contacts", "Contacts"), ("calls", "Calls"), ("emails", "Emails"),
    ("web", "Web and searches"), ("typed_words", "Typed words"), ("accounts", "Accounts and passwords"),
    ("places", "Places"), ("files", "Files and documents"), ("machine_text", "Text read from photos and audio"),
    ("other", "Other records"),
)
LABELS = dict(KINDS)
FILE_NAME_SQL = "lower(regexp_replace(f.local_path, '^.*[/\\\\]', ''))"  # = migration 20261125 ix_phone_files_name


class PhoneSearchError(ValueError):
    pass


def _kind_case():
    parts = []
    for kind, types in RECORD_KINDS.items():
        parts.append("WHEN root.model_type IN (%s) THEN '%s'" % (", ".join("'%s'" % t for t in types),
                                                              "files" if kind == "files_records" else kind))
    return "CASE %s ELSE 'other' END" % " ".join(parts)


KIND_CASE = _kind_case()


def _scope_phones(conn, case_id, phones):
    """The active phones of the case in the scope, in the case's phone order (capture order, as the phone colours)."""
    rows = conn.execute(text("SELECT id::text FROM phone_extractions WHERE case_id = :c AND standing = 'active' ORDER BY "
                             "created_at, id"), {"c": str(case_id)}).scalars().all()
    if phones:
        wanted = {str(p) for p in phones}
        unknown = wanted - set(rows)
        if unknown:
            raise PhoneSearchError("%d of the phones asked for %s not in this case." % (
                len(unknown), "is" if len(unknown) == 1 else "are"))
        rows = [r for r in rows if r in wanted]
    return rows


# ---- counts ---------------------------------------------------------------------------------------------------------

def _comm_counts(conn, case_id, q, exact, phones, start, end, first=0, labels=None):
    """Messages, calls and emails per kind and phone, and with ``first`` each kind's first ``first`` rows (in the
    order ``S._comm`` lists them) from the same match, under ``"_first"``: the match is the cost (Phone reference 1:
    each kind's own count and list ran it twice more, 3.5 s each, 26 Nov)."""
    from services.phone.filters import StreamFilter
    body = {"case_id": str(case_id), "kinds": [k for ks in COMM.values() for k in ks],
            "text": {"query": q, "exact_characters": exact}, "phones": phones}
    if start:
        body["from_instant"] = start
    if end:
        body["to_instant"] = end
    f = StreamFilter.model_validate(body)
    qy, _ = streams._query(conn, f, labels)
    params = dict(qy.params, lxf=int(first))
    grp = "CASE %s END" % " ".join("WHEN kind IN (%s) THEN '%s'" % (", ".join("'%s'" % k for k in ks), g)
                                   for g, ks in COMM.items())
    out = defaultdict(lambda: defaultdict(int))
    deleted = defaultdict(int)
    span = [None, None]
    rows = defaultdict(list)
    for r in conn.execute(text(
            "WITH m AS (%s), g AS (SELECT *, %s AS grp FROM m WHERE %s) "
            "SELECT 0 AS part, grp, extraction_id::text AS ext, count(*) AS n, count(*) FILTER (WHERE "
            "lower(coalesce(deleted_state, '')) IN ('deleted', 'trash')) AS d, min(sort_instant) AS a, "
            "max(sort_instant) AS b, NULL AS event_uid, NULL AS record_uid, NULL AS extraction_id, NULL AS thread_key, "
            "NULL AS kind, NULL AS app, NULL AS sort_instant, NULL AS body, NULL AS subject, 0 AS rn FROM g GROUP BY 2, 3 "
            "UNION ALL SELECT 1, grp, NULL, NULL, NULL, NULL, NULL, event_uid, record_uid, extraction_id, thread_key, "
            "kind, app, sort_instant, body, subject, rn FROM (SELECT g.*, row_number() OVER (PARTITION BY grp ORDER BY "
            "sort_instant NULLS LAST, event_uid) AS rn FROM g) x WHERE rn <= :lxf ORDER BY 1, 2, rn"
            % (qy.matched_sql(), grp, streams._shown(f))), params):
        if r.part == 1:
            rows[r.grp].append(r)
            continue
        out[r.grp][r.ext] += int(r.n)
        deleted[r.grp] += int(r.d)
        if r.a is not None:
            span[0] = r.a if span[0] is None else min(span[0], r.a)
            span[1] = r.b if span[1] is None else max(span[1], r.b)
    out["_span"] = span
    out["_first"] = rows
    return out, deleted


def _record_params(case_id, q, exact, phones, start, end):
    p = {"c": str(case_id), "p": phones or None, "a": start, "b": end}
    return p, S.records_match(q, exact, p)


# The record and its top-level record are read by id from the summaries: through the pv_record view Postgres hashed
# all 1.1 million summaries of every case to find the top-level records (4.2 s for "Pell" on 25 Nov, rows=5).
RECORD_FROM = ("FROM pv_text t JOIN phone_record_summaries r ON r.record_uid = t.record_uid AND r.extraction_id = "
               "t.extraction_id JOIN phone_interpretation_state st ON st.extraction_id = r.extraction_id AND st.generation "
               "= r.generation JOIN phone_record_summaries root ON root.record_uid = r.root_record_uid AND "
               "root.generation = r.generation ")
# a record of a message, call or email, or inside one, is counted with its message (Conversations), not here
NOT_COMM = ("NOT EXISTS (SELECT 1 FROM phone_comm_events e WHERE e.record_uid = t.record_uid AND e.generation = "
            "r.generation) AND NOT EXISTS (SELECT 1 FROM phone_comm_events e WHERE e.record_uid = r.parent_record_uid "
            "AND e.generation = r.generation) AND NOT EXISTS (SELECT 1 FROM phone_comm_events e WHERE e.record_uid = "
            "r.root_record_uid AND e.generation = r.generation)")


def _records_where(cond):
    # S.records_sql's conditions, on the top-level record: the record's time, comm records left to their own kinds
    return ("WHERE t.case_id = :c AND %s AND (CAST(:p AS uuid[]) IS NULL OR t.extraction_id = ANY(CAST(:p AS uuid[]))) "
            "AND (root.first_instant IS NULL OR ((CAST(:a AS timestamptz) IS NULL OR root.first_instant >= CAST(:a AS "
            "timestamptz)) AND (CAST(:b AS timestamptz) IS NULL OR root.first_instant <= CAST(:b AS timestamptz)))) "
            "AND %s" % (cond, NOT_COMM))


RECORD_ROWS = ("SELECT DISTINCT ON (root.first_instant, root.record_uid) root.record_uid, t.extraction_id, "
               "root.model_type, root.first_instant, root.deleted_state, t.value, t.is_sensitive, t.field_path, "
               "t.value_index, t.record_uid AS matched_record_uid, %s AS kind %s%s ORDER BY root.first_instant NULLS "
               "LAST, root.record_uid, t.is_sensitive, t.field_path")


def _record_counts(conn, case_id, q, exact, phones, start, end, first=0):
    """Other records per kind and phone, once per top-level record, and with ``first`` each kind's first ``first``
    rows (``_record_items``'s order) from the same match under ``"_first"``: each kind's own list ran the match
    again (Phone reference 1, "password": 4 s for the lists, 26 Nov)."""
    p, cond = _record_params(case_id, q, exact, phones, start, end)
    p["lxf"] = int(first)
    out = defaultdict(lambda: defaultdict(int))
    deleted = defaultdict(int)
    rows = defaultdict(list)
    for r in conn.execute(text(
            "WITH x AS (" + RECORD_ROWS % (KIND_CASE, RECORD_FROM, _records_where(cond)) + ") "
            "SELECT 0 AS part, kind, extraction_id::text AS ext, count(*) AS n, count(*) FILTER (WHERE "
            "lower(coalesce(deleted_state, '')) IN ('deleted', 'trash')) AS d, NULL AS record_uid, NULL AS "
            "extraction_id, NULL AS model_type, NULL AS first_instant, NULL AS deleted_state, NULL AS value, NULL AS "
            "is_sensitive, NULL AS field_path, NULL AS value_index, NULL AS matched_record_uid, 0 AS rn FROM x GROUP BY "
            "2, 3 UNION ALL SELECT 1, kind, NULL, NULL, NULL, record_uid, extraction_id, model_type, first_instant, "
            "deleted_state, value, is_sensitive, field_path, value_index, matched_record_uid, rn FROM (SELECT x.*, "
            "row_number() OVER (PARTITION BY kind ORDER BY first_instant NULLS LAST, record_uid) AS rn FROM x) y "
            "WHERE rn <= :lxf ORDER BY 1, 2, rn"), p):
        if r.part == 1:
            rows[r.kind].append(r)
            continue
        out[r.kind][r.ext] += int(r.n)
        deleted[r.kind] += int(r.d)
    out["_first"] = rows
    return out, deleted


def _file_params(case_id, q, exact, phones):
    like = S._like(q.strip().lower() if exact else F.fold(q))
    if not exact:
        # a file name keeps its dots and dashes; the folded query has spaces there, so match each folded word in order
        like = "%" + "%".join(S._like(w)[1:-1] for w in F.fold(q).split()) + "%"
    return {"c": str(case_id), "p": phones or None, "fl": like}


FILE_FROM = ("FROM phone_files f JOIN phone_extractions e ON e.id = f.extraction_id AND e.standing = 'active' WHERE "
             "e.case_id = :c AND (CAST(:p AS uuid[]) IS NULL OR f.extraction_id = ANY(CAST(:p AS uuid[]))) AND "
             "f.local_path IS NOT NULL AND " + FILE_NAME_SQL + " LIKE :fl")


def _file_counts(conn, case_id, q, exact, phones):
    out = defaultdict(int)
    deleted = 0
    for r in conn.execute(text(
            "SELECT f.extraction_id::text AS ext, count(*) AS n, count(*) FILTER (WHERE lower(coalesce((f.body -> 1) ->> "
            "'deleted', '')) IN ('deleted', 'trash')) AS d " + FILE_FROM + " GROUP BY 1"),
            _file_params(case_id, q, exact, phones)):
        out[r.ext] += int(r.n)
        deleted += int(r.d)
    return out, deleted


def _machine_counts(conn, case_id, q, exact, phones, ctx):
    out = {}
    for ext in phones:
        n, _ = S._machine(conn, case_id, q, exact, [ext], 0, 0, ctx)
        if n:
            out[ext] = n
    return out


# ---- hits -------------------------------------------------------------------------------------------------------------

def _comm_items(conn, case_id, kind, q, exact, phones, start, end, offset, limit, ctx, rows=None, titles=None):
    """A page of one kind's hits; ``rows`` the page already matched (``_comm_counts(first=...)``), ``titles`` their
    threads' titles already read (``streams.thread_titles`` reads the case's phone owners each call)."""
    if rows is None:
        total, items = S._comm(conn, case_id, kind, q, exact, phones, start, end, offset, limit, ctx)
    else:
        total, items = len(rows), S.comm_hits(conn, rows, q, exact, ctx)
    if not items:
        return total, items
    events = [i["open"]["params"]["event"] for i in items]
    extra = {str(r.event_uid): r for r in conn.execute(text(
        "SELECT event_uid, deleted_state, thread_key, extraction_id, direction FROM pv_comm_event WHERE event_uid = "
        "ANY(CAST(:u AS uuid[]))"), {"u": events})}
    if titles is None:
        titles = streams.thread_titles(conn, case_id, sorted({r.thread_key for r in extra.values() if r.thread_key}))
    for i in items:
        r = extra.get(i["open"]["params"]["event"])
        if r is None:
            continue
        thread = titles.get(r.thread_key) or {}
        i.update(event_uid=str(r.event_uid), extraction_id=str(r.extraction_id), thread_key=r.thread_key,
                 thread_title=thread.get("title"), deleted=S._is_deleted(r.deleted_state), direction=r.direction)
    return total, items


def _record_items(conn, case_id, kind, q, exact, phones, start, end, offset, limit, ctx, rows=None):
    """A page of one kind's other records; ``rows`` the page already matched (``_record_counts(first=...)``)."""
    if rows is None:
        p, cond = _record_params(case_id, q, exact, phones, start, end)
        p.update({"k": kind, "lim": limit, "off": offset})
        rows = conn.execute(text(
            "SELECT * FROM (" + RECORD_ROWS % (KIND_CASE, RECORD_FROM, _records_where(cond)) + ") x WHERE kind = :k "
            "ORDER BY first_instant NULLS LAST, record_uid LIMIT :lim OFFSET :off"), p).fetchall()
    items = S.records_items(rows, q, exact, ctx)
    for item, r in zip(items, rows):
        item["where"] = _record_where(r.model_type, S.field_name(r.field_path))
        if str(r.matched_record_uid) != str(r.record_uid):
            item["matched_record_uid"] = str(r.matched_record_uid)
    return items


WHERE_WORDS = {"Contact": "Contact", "VisitedPage": "Web page visited", "SearchedItem": "Search typed",
               "WebBookmark": "Bookmark", "Cookie": "Cookie", "DictionaryWord": "Keyboard learned word",
               "Autofill": "Autofill entry", "UserAccount": "Account", "Password": "Saved password",
               "Location": "Location", "CellTower": "Cell tower", "WirelessNetwork": "Wi-Fi network",
               "Journey": "Journey", "CalendarEntry": "Calendar entry", "Note": "Note", "Notification": "Notification",
               "InstalledApplication": "Installed app", "Chat": "Chat", "FileDownload": "File downloaded",
               "FileUpload": "File uploaded", "Recording": "Recording", "CreditCard": "Card", "SIMData": "SIM card"}


def _record_where(model_type, field_name):
    """Plain words for where a hit sits ("Contact name"); a record type with no words is split at its capitals."""
    import re
    what = WHERE_WORDS.get(model_type) or re.sub(r"(?<=[a-z])(?=[A-Z])", " ", model_type or "Record").capitalize()
    field = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", field_name or "").lower()
    return "%s %s" % (what, field) if field and field not in what.lower() else what


def _file_items(conn, case_id, q, exact, phones, offset, limit, ctx):
    p = _file_params(case_id, q, exact, phones)
    p.update({"lim": limit, "off": offset})
    out = []
    for r in conn.execute(text(
            "SELECT f.file_uid, f.extraction_id, f.local_path, f.tags AS category, (f.body -> 1) ->> 'deleted' AS "
            "deleted_state " + FILE_FROM + " ORDER BY " + FILE_NAME_SQL + ", f.file_uid LIMIT :lim OFFSET :off"), p):
        phone = ctx["phones"].get(str(r.extraction_id), "Phone")
        path = (r.local_path or "").replace("\\", "/")
        name = path.rsplit("/", 1)[-1]
        out.append({"kind": "file", "title": name, "phone_label": phone, "extraction_id": str(r.extraction_id),
                    "where": "File on the phone" + (" (%s)" % r.category if r.category else ""),
                    "snippet": S.snippet(name, q, exact) or {"before": "", "match": "", "after": name},
                    "folder": path[:-len(name)].rstrip("/") or None, "file_uid": str(r.file_uid),
                    "deleted": S._is_deleted(r.deleted_state), "record_uid": None, "time": None, "instant": None,
                    "open": {"screen": "media", "params": {"file_uid": str(r.file_uid),
                                                           "extraction_id": str(r.extraction_id)}}})
    return out


def _items(conn, case_id, kind, q, exact, phones, start, end, offset, limit, ctx, total, file_records=None,
           rows=None, titles=None):
    """A page of one kind; ``rows`` its page already matched by the counts (first page only), ``titles`` threads'
    titles already read."""
    if not total or not limit:
        return []
    if kind in COMM:
        return _comm_items(conn, case_id, kind, q, exact, phones, start, end, offset, limit, ctx, rows, titles)[1]
    if kind == "files":
        # file records (downloads, uploads, recordings) first, then the phone's files by name
        recs = file_records if file_records is not None else _record_count_of(conn, case_id, "files", q, exact,
                                                                               phones, start, end)
        items = _record_items(conn, case_id, "files", q, exact, phones, start, end, offset, limit, ctx, rows) \
            if offset < recs else []
        if len(items) < limit:
            items += _file_items(conn, case_id, q, exact, phones, max(0, offset - recs), limit - len(items), ctx)
        return items
    if kind == "machine_text":
        return S._machine(conn, case_id, q, exact, phones, offset, limit, ctx)[1]
    return _record_items(conn, case_id, kind, q, exact, phones, start, end, offset, limit, ctx, rows)


def _record_count_of(conn, case_id, kind, q, exact, phones, start, end):
    counts, _ = _record_counts(conn, case_id, q, exact, phones, start, end)
    return sum(counts.get(kind, {}).values())


# ---- saved differently -------------------------------------------------------------------------------------------------

def saved_differently(conn, case_id, q, exact, phones, ctx):
    """People the query finds whom the phones in scope save under different names: ``[{identity_key, person_id,
    names: [{extraction_id, phone, names}], own_phones: [{extraction_id, phone}], sentence}]``. Built from the phones'
    contact records (identity names with a contact basis); identities linked to one person are read together."""
    fq = F.fold(q, exact=exact)
    if len(fq.replace(" ", "")) < S.MIN_TEXT and not S._digits(q):
        return []
    _, hits = S._people(conn, case_id, q, exact, False, 0, 10_000)
    keys = [h["identity_key"] for h in hits if h.get("identity_key")]
    known = {h["identity_key"]: h.get("names") or [] for h in hits if h.get("identity_key")}
    if not keys:
        return []
    rows = conn.execute(text(
        "SELECT i.identity_key, i.person_id, n.extraction_id::text AS ext, n.name FROM pv_identity i JOIN "
        "pv_identity_name n ON n.identity_id = i.identity_id WHERE i.case_id = :c AND n.case_id = :c AND n.basis IN "
        "('contact', 'contact_entry') AND (i.identity_key = ANY(:k) OR i.person_id IN (SELECT person_id FROM "
        "pv_identity WHERE case_id = :c AND identity_key = ANY(:k) AND person_id IS NOT NULL)) ORDER BY 1, 3, 4"),
        {"c": str(case_id), "k": keys}).fetchall()
    who = defaultdict(lambda: {"keys": set(), "names": defaultdict(set)})
    for r in rows:
        if phones and r.ext not in phones:
            continue
        g = who[str(r.person_id) if r.person_id else r.identity_key]
        g["keys"].add(r.identity_key)
        g["person_id"] = str(r.person_id) if r.person_id else None
        g["names"][r.ext].add(r.name)
    owners = {ext: set(o.get("keys") or []) for ext, o in ctx["labels"].owners.items()}
    order = {e: i for i, e in enumerate(phones or [])}
    out = []
    for gid, g in who.items():
        folded = {ext: {F.fold(n) for n in ns} for ext, ns in g["names"].items()}
        if len(folded) < 2 or len({frozenset(v) for v in folded.values()}) < 2:
            continue  # saved on one phone only, or the same way on each
        own = sorted((ext for ext, ks in owners.items() if ks & g["keys"] and (not phones or ext in phones)),
                     key=lambda e: order.get(e, 99))
        names = [{"extraction_id": ext, "phone": ctx["phones"].get(ext, "Phone"), "names": sorted(ns)}
                 for ext, ns in sorted(g["names"].items(), key=lambda kv: order.get(kv[0], 99))]
        # the name to call them by: one holding the words searched for, else the longest name a phone saves
        every = {n for x in names for n in x["names"]} | {n for k in g["keys"] for n in known.get(k, [])}
        shown = sorted(every, key=lambda n: (fq not in F.fold(n), -len(n), n))
        sentence = ". ".join("%s: %s" % (x["phone"], ", ".join("“%s”" % n for n in x["names"])) for x in names)
        if own:
            sentence += ". %s %s this person's own phone" % (" and ".join(ctx["phones"].get(e, "Phone") for e in own),
                                                            "is" if len(own) == 1 else "are")
        out.append({"identity_keys": sorted(g["keys"]), "person_id": g.get("person_id"), "names": names,
                    "own_phones": [{"extraction_id": e, "phone": ctx["phones"].get(e, "Phone")} for e in own],
                    "name": shown[0], "sentence": sentence + "."})
    out.sort(key=lambda x: (-len(x["names"]), x["name"]))
    return out


# ---- next steps ---------------------------------------------------------------------------------------------------------

def next_steps(q, kinds, phones, saved, limits, deleted_total, elsewhere, ctx, span=(None, None)):
    """Ranked next steps built from this result (COMMON rule 4): each a title, a why from the result's own numbers,
    and what to open with the people, phones and period filled in. Rules, in rank order:
    a person saved differently, deleted items found, the same words in the case's other sources, phones with
    nothing found while others have hits, a question over the results, keeping the words as a keyword list."""
    steps = person_steps(saved)
    total = sum(k["total"] for k in kinds)
    if deleted_total:
        steps.append({"id": "deleted", "title": "Read the %s deleted %s first" % (
            "{:,}".format(deleted_total), "item" if deleted_total == 1 else "items"),
            "why": "%s of the %s results %s deleted on the phone and recovered by the extraction." % (
                "{:,}".format(deleted_total), "{:,}".format(total), "was" if deleted_total == 1 else "were"),
            "open": {"screen": "conversations", "params": {"q": q, "deleted": "1"}}})
    other = [(k, n) for k, n in (elsewhere or {}).items() if n]
    if other:
        words = {"payments": "payment", "documents": "document"}
        parts = ["%s %s%s" % ("{:,}".format(n), words.get(k, k), "" if n == 1 else "s") for k, n in other]
        steps.append({"id": "corroborate", "title": "Check it against the rest of the case",
                      "why": "The same words are in %s outside the phones." % " and ".join(parts),
                      "open": {"screen": "corroborate", "params": {"q": q}}})
    if total:
        found = {e for k in kinds for e, n in k["by_phone"].items() if n}
        empty = [e for e in phones if e not in found]
        if empty and found:
            names = ", ".join(ctx["phones"].get(e, "Phone") for e in empty)
            when = {}
            if span[0] is not None:
                when = {"from": span[0].date().isoformat(), "to": span[1].date().isoformat()}
                said = (_day_words(span[0]), _day_words(span[1]))
            steps.append({"id": "empty_phones", "title": "See what %s %s on the same dates" % (
                              names, "holds" if len(empty) == 1 else "hold"),
                          "why": "%s %s no result for these words while %d other %s %s%s." % (
                              names, "has" if len(empty) == 1 else "have", len(found),
                              "phone" if len(found) == 1 else "phones", "has" if len(found) == 1 else "have",
                              " results from %s to %s" % said if when else ""),
                          "open": {"screen": "timeline", "params": dict({"phones": ",".join(empty)}, **when)}})
        steps.append({"id": "ask", "title": "Ask a question about these results",
                      "why": "%s results on %d %s; a question reads them all and cites each record it uses." % (
                          "{:,}".format(total), len(found), "phone" if len(found) == 1 else "phones"),
                      "open": {"screen": "ask", "params": {"q": q}}})
        steps.append({"id": "keyword_list", "title": "Keep watching for “%s”" % q,
                      "why": "Saved as a keyword list, the words run on every phone of the case, including phones "
                             "added later.", "open": {"screen": "keyword_list", "params": {"q": q}}})
    if limits:
        steps.insert(0, {"id": "limits", "title": "Search again when every phone is read",
                         "why": "%d %s still being read, so these counts can grow." % (
                             len(limits), "phone is" if len(limits) == 1 else "phones are"),
                         "open": {"screen": "phones", "params": {}}})
    for rank, s in enumerate(steps, 1):
        s["rank"] = rank
    return steps


def person_steps(saved):
    """The first next steps: open each of the first two people saved differently across every phone."""
    return [{"id": "person", "title": "Open %s across every phone" % s["name"],
             "why": "Saved under different names on %d phones: %s" % (len(s["names"]), s["sentence"]),
             "open": {"screen": "person", "params": {"people": ",".join(s["identity_keys"]),
                                                     "person_id": s["person_id"]}}} for s in saved[:2]]


def people_step(conn, case_id, q, *, exact=False, phones=None) -> dict:
    """The people the words find whom the phones save under different names, and their next steps, on their own:
    ``{saved_differently, steps}``. The screen asks it beside the first results (``phone_search(people=False)``):
    it folds the names of the case's identities that could hold the words, 1.2 to 1.5 s of the first results on
    Phone reference 1 (26 Nov)."""
    q = _check(q)
    scope = _scope_phones(conn, case_id, phones)
    if len(F.fold(q, exact=exact).replace(" ", "")) < S.MIN_TEXT or not scope:
        return {"saved_differently": [], "steps": []}
    saved = saved_differently(conn, case_id, q, exact, scope, S._context(conn, case_id))
    return {"saved_differently": saved, "steps": person_steps(saved)}


def _day_words(dt):
    return "%d %s %d" % (dt.day, dt.strftime("%b"), dt.year)


# ---- entry points --------------------------------------------------------------------------------------------------------

def _check(q, limit=FIRST):
    q = (q or "").strip()
    if not q:
        raise PhoneSearchError("Type something to search for.")
    if not 1 <= limit <= MAX_PAGE:
        raise PhoneSearchError("A page holds 1 to 200 results.")
    return q


def period(conn, case_id, start, end):
    """The scope's dates (``YYYY-MM-DD``, as the phone screens carry them) as instants: from the start of the first
    day to the end of the last, in the case's display zone. An instant is used as given."""
    from datetime import date, timedelta
    zone = streams.case_zone(conn, case_id)["name"]
    out = []
    for value, last in ((start, False), (end, True)):
        if not value:
            out.append(None)
            continue
        try:
            day = date.fromisoformat(value)
        except ValueError:
            out.append(value)  # an instant
            continue
        a, b = T.day_bounds(day, zone)
        out.append((b - timedelta(microseconds=1)) if last else a)
    return out


def phone_search(conn, case_id, q, *, exact=False, phones=None, start=None, end=None, elsewhere=False,
                 people=True) -> dict:
    """The first results. ``elsewhere`` (off for the screen) also counts the words in the case's documents and
    payments: that count read every document text of a case (19 s on Demo 2, 25 Nov), so the screen asks
    ``elsewhere_step`` after the first results instead. ``people`` off leaves the people saved differently and
    their steps to ``people_step``, asked beside (``people_pending`` says so)."""
    q = _check(q)
    scope = _scope_phones(conn, case_id, phones)
    start, end = period(conn, case_id, start, end)
    ctx = S._context(conn, case_id)
    short = len(F.fold(q, exact=exact).replace(" ", "")) < S.MIN_TEXT
    counts, deleted = defaultdict(dict), defaultdict(int)
    file_records = 0
    span = [None, None]
    first_rows = {}
    if not short and scope:
        comm = _comm_counts(conn, case_id, q, exact, scope, start, end, first=FIRST, labels=ctx["labels"])
        span = comm[0].pop("_span")
        first_rows = comm[0].pop("_first")
        recs = _record_counts(conn, case_id, q, exact, scope, start, end, first=FIRST)
        first_rows.update(recs[0].pop("_first"))
        for src in (comm, recs):
            for kind, per in src[0].items():
                for ext, n in per.items():
                    counts[kind][ext] = counts[kind].get(ext, 0) + n
            for kind, n in src[1].items():
                deleted[kind] += n
        file_records = sum(counts.get("files", {}).values())
        files, fdel = _file_counts(conn, case_id, q, exact, scope)
        for ext, n in files.items():
            counts["files"][ext] = counts["files"].get(ext, 0) + n
        deleted["files"] += fdel
        counts["machine_text"] = _machine_counts(conn, case_id, q, exact, scope, ctx)
    # the threads of every message, call and email shown, titled in one read
    keys = sorted({r.thread_key for k in COMM for r in first_rows.get(k, []) if r.thread_key})
    titles = streams.thread_titles(conn, case_id, keys, ctx["labels"]) if keys else {}
    kinds, groups = [], []
    for kind, label in KINDS:
        per = {ext: int(counts.get(kind, {}).get(ext, 0)) for ext in scope}
        total = sum(per.values())
        kinds.append({"kind": kind, "label": label, "total": total, "by_phone": per,
                      "deleted": int(deleted.get(kind, 0))})
        if total:
            items = _items(conn, case_id, kind, q, exact, scope, start, end, 0, FIRST, ctx, total, file_records,
                           first_rows.get(kind, []) if kind != "machine_text" else None, titles)
            groups.append({"kind": kind, "label": label, "total": total, "items": items,
                           "next_cursor": str(len(items)) if len(items) < total else None})
    limits = S.coverage_limits(conn, case_id, scope)
    saved = [] if short or not people else saved_differently(conn, case_id, q, exact, scope, ctx)
    other = _elsewhere(conn, case_id, q, exact) if elsewhere and not short else {}
    total = sum(k["total"] for k in kinds)
    return {"query": q, "folded_query": F.fold(q, exact=exact), "exact": exact, "short": S.SHORT if short else None,
            "number_digits": None if exact else S.number_words.number_digits(q),
            "phones": [{"extraction_id": e, "label": ctx["phones"].get(e, "Phone")} for e in scope],
            "total": total, "kinds": kinds, "groups": groups, "saved_differently": saved,
            "people_pending": bool(not people and not short and scope),
            "elsewhere": other, "complete": not limits, "limits": limits,
            "period": {"from": T.iso(span[0]), "to": T.iso(span[1])},
            "next_steps": next_steps(q, kinds, scope, saved, limits, sum(deleted.values()), other, ctx, span),
            "not_searched": S.NOT_SEARCHED + [{"group": "long_texts", "reason": (
                "A number written with spaces inside an email or text longer than 1,000 characters is found when you "
                "type it as it is written there.")}]}


def elsewhere_step(conn, case_id, q, *, exact=False) -> dict:
    """The corroborate next step on its own: the same words in the case's documents and payments, with the step
    ``next_steps`` would rank (None when neither holds them)."""
    q = _check(q)
    short = len(F.fold(q, exact=exact).replace(" ", "")) < S.MIN_TEXT
    counts = {} if short else _elsewhere(conn, case_id, q, exact)
    steps = [s for s in next_steps(q, [], [], [], [], 0, counts, None) if s["id"] == "corroborate"]
    return {"query": q, "counts": counts, "step": steps[0] if steps else None}


def _elsewhere(conn, case_id, q, exact):
    """The same words in the case's documents and payments (counts only), for the corroborate step."""
    out = {}
    for group in ("documents", "payments"):
        try:
            g = S._group(conn, case_id, group, q, exact, None, None, None, 0, 0, {"phones": {}, "zone": "UTC",
                                                                               "labels": None}, False)
            out[group] = int(g.get("total") or 0)
        except Exception:  # a source that cannot be counted is left out of the step, never the search
            out[group] = 0
    return out


def kind_page(conn, case_id, q, kind, *, cursor=None, limit=MAX_PAGE, exact=False, phones=None, start=None,
              end=None) -> dict:
    """The next page of one kind's hits, in the same order and with the same total as ``phone_search``."""
    q = _check(q, limit)
    if kind not in LABELS:
        raise PhoneSearchError("No kind of record called %s." % kind)
    scope = _scope_phones(conn, case_id, phones)
    start, end = period(conn, case_id, start, end)
    ctx = S._context(conn, case_id)
    offset = int(cursor or 0)
    if kind in COMM:
        total = sum(_comm_counts(conn, case_id, q, exact, scope, start, end)[0].get(kind, {}).values())
    elif kind == "files":
        total = _record_count_of(conn, case_id, "files", q, exact, scope, start, end) + sum(
            _file_counts(conn, case_id, q, exact, scope)[0].values())
    elif kind == "machine_text":
        total = sum(_machine_counts(conn, case_id, q, exact, scope, ctx).values())
    else:
        total = _record_count_of(conn, case_id, kind, q, exact, scope, start, end)
    items = _items(conn, case_id, kind, q, exact, scope, start, end, offset, limit, ctx, total)
    limits = S.coverage_limits(conn, case_id, scope)
    return {"kind": kind, "label": LABELS[kind], "total": total, "items": items, "complete": not limits,
            "limits": limits, "next_cursor": str(offset + len(items)) if offset + len(items) < total else None}


def hit_context(conn, case_id, event_uid, *, before=3, after=3) -> dict:
    """A message, call or email hit in its thread: the thread's title, phone and size, and the messages around it in
    thread order, the hit marked (screen 2's "In context")."""
    from services.phone.filters import StreamFilter
    ev = conn.execute(text("SELECT event_uid, extraction_id::text AS ext, thread_key, deleted_state FROM pv_comm_event "
                           "WHERE case_id = :c AND event_uid = CAST(:u AS uuid)"),
                      {"c": str(case_id), "u": str(event_uid)}).first()
    if ev is None:
        raise LookupError("That message is not in this case.")
    body = {"case_id": str(case_id), "phones": [ev.ext]}
    if ev.thread_key:
        body["threads"] = [ev.thread_key]
    else:
        before = after = 0  # a record in no conversation is shown alone, not beside unrelated messages
    f = StreamFilter.model_validate(body)
    qy, lctx = streams._query(conn, f)
    zone = streams.resolve_zone(conn, f)["name"]
    # the thread in its order across days (a window of one day cut a thread at midnight), the hit in the middle
    qy.params.update(t=str(ev.event_uid), lo=int(before), hi=int(after))
    rows = conn.execute(text(
        "WITH m AS (%s), s AS (SELECT *, row_number() OVER (ORDER BY sort_instant NULLS LAST, event_uid) AS rn FROM m "
        "WHERE %s OR event_uid = CAST(:t AS uuid)), at AS (SELECT rn FROM s WHERE event_uid = CAST(:t AS uuid)) "
        "SELECT s.* FROM s, at WHERE s.rn BETWEEN at.rn - :lo AND at.rn + :hi ORDER BY s.rn"
        % (qy.matched_sql(), streams._shown(f))), qy.params).fetchall()
    total = streams.shown_count(conn, f) if ev.thread_key else None
    items = streams.build_rows(conn, lctx, rows, zone, f)
    ctx = S._context(conn, case_id)
    title = (streams.thread_titles(conn, case_id, [ev.thread_key], lctx).get(ev.thread_key) or {}).get("title") \
        if ev.thread_key else None
    # the hit's day in the zone the screen shows times in, as the date and its first and last instant ("That day,
    # all phones"): the UTC date of the instant is the day before or after near midnight
    day = S.day_of(next((r.sort_instant for r in rows if str(r.event_uid) == str(ev.event_uid)), None), zone)
    return {"event_uid": str(ev.event_uid), "extraction_id": ev.ext, "phone": ctx["phones"].get(ev.ext, "Phone"),
            "thread_key": ev.thread_key, "thread_title": title, "thread_count": total,
            "deleted": S._is_deleted(ev.deleted_state), "items": items, "day": day,
            "note": None if ev.thread_key else "This record is in no conversation; it is shown alone."}
