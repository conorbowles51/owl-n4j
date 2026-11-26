"""Cast a wide net (plan R2b): every candidate from every kind of case material, each with its whole text.

Lists gathered, each in its own order:
- meaning and words over every embedded area (``embed_all.search.meaning_hits`` / ``word_hits``): phone message
  windows, ledger rows, accounts, judgement calls, trails, statement pages, notes and findings, timeline, parties,
  transcripts, document passages. Run for the question, for each other phrasing (meaning only) and for each name
  expansion (words only);
- documents by their words (``meaning_search.word_search_documents``), which the embedded-area word search does not
  cover;
- graph entities by name, key, summary and alias (``graph_service.search_nodes``, once per name or identifier) and by
  meaning (the entity vectors).

The lists are fused by reciprocal rank fusion (``retrieval_fusion.K``). Each candidate keeps the text the source
returned in full (``text``); ``units`` makes it a whole unit and ``rerank`` reads an excerpt of it.
"""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from services.retrieval_fusion import K

logger = logging.getLogger(__name__)

# meaning searches of one question run side by side (the question, its dated areas, three phrasings, the graph);
# each sends its own Chroma queries side by side too (embed_all.search.QUERY_WORKERS), so this stays small
POOL_WORKERS = 4

# The kinds a caller asks for, and the embedded areas each covers.
KIND_AREAS: dict[str, tuple[str, ...]] = {
    "phones": ("phone_text", "parties", "transcripts"),
    "documents": ("documents", "statement_pages"),
    "ledger": ("ledger", "accounts", "judgements", "trails"),
    "graph": ("relationships",),
    "timeline": ("timeline",),
    "casework": ("casework",),
}
KINDS = tuple(KIND_AREAS)
AREA_KIND = {a: k for k, areas in KIND_AREAS.items() for a in areas}
KIND_LABEL = {"phone_text": "phone messages", "parties": "phone contact", "transcripts": "transcript",
              "documents": "document passage", "statement_pages": "statement page", "ledger": "statement row",
              "accounts": "bank account", "judgements": "judgement call", "trails": "money trail",
              "timeline": "timeline event", "casework": "note or finding", "graph": "graph entity",
              "relationships": "graph connection"}
FETCH = 60
GRAPH_TERMS = 4
# entities read per name: a surname such as "Ruiz" names companies, places and events too (demo case: 10 a name left
# Lucia Ruiz out, lx-searchfix 18 Nov)
GRAPH_FETCH = 25
FAMILY = re.compile(r"\b(famil(y|ies)|household|relatives|relations|siblings|brothers|sisters|parents|kids|children|"
                    r"cousins|in-laws)\b", re.I)


def _names_it(node: dict, probe: str) -> bool:
    """Whether a graph name lookup's hit holds the name as words, not inside another word or an id: the graph's
    lookup matches any part of the text, so "Dee" found entities whose id holds "7ae67dee63ee" (demo, 18 Nov)."""
    from services.phone import fold as F
    want = F.fold(probe)
    if not want:
        return False
    if (node.get("key") or "") == probe:
        return True
    aliases = node.get("aliases") or []
    hay = " %s " % F.fold(" ".join(str(x) for x in [node.get("name"), node.get("summary"), node.get("notes")]
                                    + (aliases if isinstance(aliases, list) else [aliases]) if x))
    # a word, a phrase, or the start of a word ("Dee" in "dee_o28")
    return (" %s" % want) in hay


def _rrf(lists: list[list[dict]]) -> list[dict]:
    """One list from many: a candidate scores sum(1 / (K + rank)) over the lists it is in; its sources are kept."""
    score: dict[tuple, float] = {}
    best: dict[tuple, dict] = {}
    for lst in lists:
        for rank, h in enumerate(lst, 1):
            k = (h["area"], h["key"])
            score[k] = score.get(k, 0.0) + 1.0 / (K + rank)
            if k not in best:
                best[k] = dict(h, sources=set(h.get("sources") or ()))
            else:
                b = best[k]
                b["sources"] |= set(h.get("sources") or ())
                if len(h.get("text") or "") > len(b.get("text") or ""):
                    b["text"] = h["text"]
    out = []
    for k in sorted(score, key=lambda k: -score[k]):
        h = best[k]
        h["fused"] = round(score[k], 6)
        h["sources"] = sorted(h["sources"])
        out.append(h)
    return out


def _merge_meaning(hits: list[dict]) -> list[dict]:
    """One meaning list over every area: areas take turns (each area's best, then each area's second), nearest first
    within a turn, as the embedded-records search fuses. Two lists joined end to end put every phone message and
    document passage below every other area's hit."""
    return sorted(hits, key=lambda h: (h.get("area_rank", 1), h["distance"]))


def _take_turns(lists: list[list[dict]]) -> list[dict]:
    """One list from several, each giving its next hit in turn; a hit already taken is not taken again."""
    out: list[dict] = []
    seen: set[tuple] = set()
    for i in range(max((len(x) for x in lists), default=0)):
        for lst in lists:
            if i < len(lst):
                k = (lst[i]["area"], lst[i]["key"])
                if k not in seen:
                    seen.add(k)
                    out.append(lst[i])
    return out


def without_name(question: str, name: str) -> str:
    """The question with a person's name taken out ("What payments did Lena Marsh receive?" gives "What payments did
    receive?"): on her own phone every message carries her name, so the rest of the question ranks them."""
    q = question or ""
    for w in sorted(set(name.split()), key=len, reverse=True):
        q = re.sub(r"(?<!\w)%s(?:'s)?(?!\w)" % re.escape(w), " ", q, flags=re.I)
    q = re.sub(r"\s+", " ", q).strip()
    return q or question


def own_tag(o: dict) -> str:
    return " (%s's own phone)" % o["name"]


def _own_phone_list(conn, case_id, question, own, *, person=None) -> list[dict]:
    """One list over the named people's own phones (``understand.own_phones``), the phones taking turns; within a
    phone, meaning and words fused. Messages already found elsewhere stay where they are: this is one more list."""
    per_phone: list[list[dict]] = []
    for o, fut in own:
        _, w, _ = _embedded(conn, case_id, without_name(question, o["name"]), ["phone_text"], embed_query=None,
                            collections=None, meaning=False, phone=o["extraction_id"], person=person, tag=own_tag(o))
        m: list[dict] = []
        if fut is not None:
            m, _ = fut.result()
        per_phone.append(_rrf([x for x in (m, w) if x]))
    return _take_turns(per_phone)


def _merge_words(hits: list[dict]) -> list[dict]:
    """More question words first; within one count, areas take turns (each area's first, then each area's second), as
    in the meaning list. One list by count alone let 30 graph connections holding one word of the question fill a
    block ahead of every other area's one-word hit."""
    by_count: dict[int, dict[str, list[dict]]] = {}
    for h in hits:
        by_count.setdefault(h.get("words", 0), {}).setdefault(h.get("area") or "", []).append(h)
    out: list[dict] = []
    for n in sorted(by_count, reverse=True):
        areas = list(by_count[n].values())
        for i in range(max(len(a) for a in areas)):
            out += [a[i] for a in areas if i < len(a)]
    return out


def _meaning(case_id, query, areas, *, embed_query, collections, phone=None, person=None, date_from=None,
             date_to=None, tag="") -> tuple[list[dict], list[str]]:
    """One meaning search (embedding and vector store, no database connection), so several can run side by side."""
    from services.embed_all import search as ES
    try:
        vec = embed_query(query)
        m = ES.meaning_hits(case_id, vec, collections[0], collections[1], list(areas), phone=phone, person=person,
                            date_from=date_from, date_to=date_to)
        m.sort(key=lambda h: (h.get("area_rank", 1), h["distance"]))
        for h in m:
            h["sources"] = ["meaning" + tag]
        return m, []
    except Exception as exc:  # noqa: BLE001
        try:
            from services.meaning_search import describe_failure
            reason = describe_failure(exc)[1]
        except Exception:  # noqa: BLE001
            reason = str(exc)[:160]
        return [], ["Meaning search unavailable (%s); searched the words only." % reason]


def _embedded(conn, case_id, query, areas, *, embed_query, collections, words=True, meaning=True, phone=None,
              person=None, date_from=None, date_to=None, tag="", ready=None, exact=False
              ) -> tuple[list[dict], list[dict], list[str]]:
    """Meaning and words for one query; ``ready`` is the meaning search's future when it already runs elsewhere.
    Words are loose (``loose.groups``: stems, statement abbreviations, generic money words dropped) unless
    ``exact``."""
    from services.embed_all import search as ES
    from services.phone import chat_retrieval
    notes: list[str] = []
    m: list[dict] = []
    w: list[dict] = []
    if ready is not None:
        m, notes = ready.result()
        notes = list(notes)
    elif meaning and collections is not None:
        m, notes = _meaning(case_id, query, areas, embed_query=embed_query, collections=collections, phone=phone,
                            person=person, date_from=date_from, date_to=date_to, tag=tag)
        notes = list(notes)
    if words:
        terms = chat_retrieval.terms(query)
        if not exact:
            from services.case_search import loose
            terms = loose.groups(terms)
        try:
            w = ES.word_hits(conn, case_id, terms, list(areas), phone=phone, person=person, date_from=date_from,
                             date_to=date_to)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Word search failed", exc_info=True)
            notes.append("Word search of the embedded records failed (%s)." % str(exc)[:160])
            w = []
        w.sort(key=lambda h: -h.get("words", 0))
        for h in w:
            h["sources"] = ["words" + tag]
    return m, w, notes


def _documents_by_words(conn, case_id, query) -> tuple[list[dict], dict]:
    from sqlalchemy.orm import Session

    from sqlalchemy import text

    from services.meaning_search import word_search_documents
    # Phone conversation files are searched by their message windows (the embedded-area word search); reading them
    # again here cost 11 s a term on the demo case under load (91 of 243 s, profiled 17 Nov).
    ids = [r[0] for r in conn.execute(text(
        "SELECT id FROM evidence_files WHERE case_id = :c AND deleted_at IS NULL AND coalesce(source_type, '') <> "
        "'phone_text'"), {"c": str(case_id)})]
    if not ids:
        return [], {"total_documents": 0, "terms": [], "not_searched": []}
    with Session(bind=conn) as db:
        found = word_search_documents(db, case_id=case_id, query=query, limit=20, offset=0, snippet_context=1200,
                                      max_matches_per_document=3, evidence_ids=ids)
    out = []
    for doc in found.get("documents") or []:
        for mt in doc.get("matches") or []:
            page = mt.get("page_number")
            out.append({"area": "documents", "key": "%s:p%s:%s" % (doc["evidence_file_id"], page, mt.get("start_char")),
                        "title": doc.get("filename") or "", "text": mt.get("snippet") or "",
                        "cite": "doc://%s/%s" % (doc["evidence_file_id"], page or ""), "person": "", "as_read": False,
                        "sources": ["document words"], "page": page})
    return out, {"total_documents": found.get("total_documents"), "terms": found.get("terms_searched"),
                 "not_searched": found.get("terms_not_searched")}


def _graph(case_id, query, names, terms, *, embed_query, expansions=(), only_graph=False
           ) -> tuple[list[dict], list[dict], list[str]]:
    """Graph entities by name (the question's names and identifiers, the other names phones save for them, people
    whose initials the question gives) and by meaning."""
    notes: list[str] = []
    by_words: list[dict] = []
    seen: dict[str, dict] = {}
    found_runs: set[str] = set()
    try:
        from services.case_search.understand import initials, name_initials
        from services.neo4j.graph_service import graph_service
        # names and identifiers only (a plate, a check number): an ordinary word such as "patients" names every
        # entity holding it (demo second case, 17 Nov: 18 of a question's first 64 places), and meaning covers it.
        # A name's other names (lx-searchfix D: "Dee" is saved as "Desmond Okafor" on another phone) come after the
        # names themselves.
        own = [n for n in names if not initials(n)]
        tied = [e["term"] for e in expansions or () if e.get("kind") in ("contact_name", "person")]
        probes = list(dict.fromkeys(own + [t for t in terms if any(ch.isdigit() for ch in t)]))[:GRAPH_TERMS]
        probes += [t for t in dict.fromkeys(tied) if t not in probes][:GRAPH_TERMS]
        why: dict[str, str] = {e["term"]: "%s: %s" % (e["name"], e["basis"]) for e in expansions or ()
                               if e.get("kind") in ("contact_name", "person")}
        wanted = [initials(n) for n in names if initials(n)]
        if wanted:
            for n in graph_service.person_names(str(case_id)):
                if name_initials(n.get("name") or "") in wanted:
                    probes.append(n["name"])
                    why[n["name"]] = "the initials %s are this person's" % ", ".join(
                        x for x in names if initials(x))
        # a single word of a full name the question gives ("Halloran" of "Priya Halloran") also finds other people of
        # that name: its hits come after the full name's, never in place of them
        runs = [p for p in probes if " " in p]
        weight = {p: (0 if " " not in p and any(p in r.split() for r in runs) else 1) for p in probes}
        family = bool(FAMILY.search(query or ""))
        if family:
            # "Ruiz family": the people who share the surname first, each saying so (lx-searchfix D)
            from services.phone import fold as F
            surnames = {F.fold(n) for n in own if " " not in n}
            for n in graph_service.person_names(str(case_id)):
                words = F.fold(n.get("name") or "").split()
                if words and words[-1] in surnames and n["name"] not in probes:
                    probes.insert(0, n["name"])
                    weight[n["name"]] = 2
                    why[n["name"]] = "shares the surname %s" % words[-1].title()
        for p in probes:
            # the graph search alone (search_graph_entities) asks for whom the name names: a part of a full name that
            # was found is not looked up (gate 18 Nov: "Priya Halloran" listed Paul Halloran in the top 10)
            if only_graph and weight.get(p) == 0 and any(p in r.split() for r in found_runs):
                continue
            for n in graph_service.search_nodes(p, limit=GRAPH_FETCH, case_id=str(case_id)):
                key = n.get("key")
                if not key or not _names_it(n, p):
                    continue
                if " " in p:
                    found_runs.add(p)
                w = weight.get(p, 1)
                if key in seen:
                    seen[key]["words"] += w
                    continue
                h = {"area": "graph", "key": key, "title": "%s (%s)" % (n.get("name") or key, n.get("type") or "entity"),
                     "cite": "entity://%s" % key, "person": n.get("name") or "", "as_read": True,
                     "text": " ".join(x for x in (n.get("name"), n.get("summary")) if x), "words": w,
                     "sources": ["graph names"], "node": dict(n)}
                if p in why:
                    h["found_by"] = why[p]
                seen[key] = h
                by_words.append(h)
        by_words.sort(key=lambda h: -h["words"])
    except Exception as exc:  # noqa: BLE001
        notes.append("Graph entities could not be searched by name (%s)." % str(exc)[:160])
    by_meaning: list[dict] = []
    try:
        from services.vector_db_service import get_vector_db_service
        res = get_vector_db_service().search_entities(embed_query(query), top_k=20,
                                                      filter_metadata={"case_id": str(case_id)})
        from services.embed_all.search import MAX_DISTANCE
        for r in res or []:
            # the meaning search's own cutoff, as for every other area's hit
            if not r.get("id") or r.get("distance") is None or r["distance"] > MAX_DISTANCE:
                continue
            by_meaning.append({"area": "graph", "key": r["id"], "distance": r.get("distance") or 0.0,
                               "area_rank": len(by_meaning) + 1, "title": (r.get("metadata") or {}).get("name") or r["id"],
                               "cite": "entity://%s" % r["id"], "person": "", "as_read": True,
                               "text": r.get("text") or "", "sources": ["graph meaning"]})
    except Exception as exc:  # noqa: BLE001
        notes.append("Graph entities could not be searched by meaning (%s)." % str(exc)[:160])
    if only_graph and found_runs:
        _tag_other_names(by_meaning, seen, found_runs)
    return by_words, by_meaning, notes


def _tag_other_names(by_meaning: list[dict], seen: dict, found_runs: set) -> None:
    """In the graph search alone, a full name the question gives was found: a hit by meaning alone whose name holds a
    word of that name but not the name is another entity sharing the word ("Pell Hardware" for "Dorian Pell"; gate
    18 Nov, rank 6 of 25). It says so in ``other_name``, and the graph tool lists it after the rest."""
    from services.phone import fold as F
    runs = [(r, F.fold(r)) for r in found_runs]
    for h in by_meaning:
        if h["key"] in seen:
            continue
        title = " %s " % F.fold(h.get("title") or "")
        for run, folded in runs:
            if " %s " % folded in title:
                break
            shared = [w for w in folded.split() if " %s " % w in title]
            if shared:
                h["other_name"] = "holds %s of the name %s, not the name" % (" ".join(shared).title(), run)
                break


def gather(conn, case_id, question: str, understood: dict, kinds: tuple[str, ...], *, areas=None, phone=None,
           person=None,
           date_from=None, date_to=None, embed_query: Callable[[str], list[float]] | None = None,
           collections=None, exact: bool = False) -> dict[str, Any]:
    """Every candidate, fused, with ``searched``/``not_searched``/``notes`` for the result."""
    notes: list[str] = []
    searched: list[str] = []
    not_searched: list[str] = []
    only = set(areas or ())
    # "entities" (the embedded-records search's name for the entity vectors) is the graph's entity search here;
    # "graph" asks for entities and their connections, "relationships" for the connections alone
    if "graph" in only:
        only.add("relationships")
    if "entities" in only:
        only.add("graph")
    entities = "graph" in kinds and (not only or "graph" in only)
    if only:
        kinds = tuple(k for k in kinds if k != "graph" or "graph" in only or "relationships" in only)
    areas = [a for k in kinds for a in KIND_AREAS[k] if not only or a in only]
    if date_from is not None or date_to is not None:
        notes.append("Only records dated inside the dates asked for were searched; phone messages and document "
                     "passages carry no single date, so they were searched without the dates.")
    cache: dict[str, list[float]] = {}
    base_embed = embed_query

    def embed(q: str) -> list[float]:
        nonlocal base_embed
        if q not in cache:
            if base_embed is None:
                from services.embedding_service import EmbeddingService
                base_embed = EmbeddingService().generate_embedding
            cache[q] = base_embed(q)
        return cache[q]

    if collections is None and areas:
        try:
            from services.embed_all.core import COLLECTION
            from services.vector_db_service import get_vector_db_service
            svc = get_vector_db_service()
            collections = (svc.client.get_or_create_collection(name=COLLECTION), svc.chunk_collection)
        except Exception as exc:  # noqa: BLE001
            notes.append("Meaning search unavailable (the vector store did not answer: %s); searched the words only."
                         % str(exc)[:120])
            collections = None
    # one meaning list and one word list over every area, graph entities included, each area taking its turn; a
    # source given a list of its own would rank its first hit beside the best of all the others (gate 17 Nov: graph
    # entities held 30 of a question's first 60 places)
    clock: dict[str, float] = {}
    meaning_ok = collections is not None
    dated = [a for a in areas if a in ("phone_text", "documents")]
    undated = [a for a in areas if a not in ("phone_text", "documents")]
    t0 = time.time()
    # The meaning searches (the question, its dated areas, each phrasing) and the graph search need no database
    # connection: they run side by side while the word searches use this one (live, 17 Nov, load 41: five meaning
    # calls in a row took 17.5 s of a 70 s search). Their results are read in the order the calls were made.
    pool = ThreadPoolExecutor(max_workers=POOL_WORKERS)
    if meaning_ok and areas and base_embed is None:
        try:
            from services.embedding_service import EmbeddingService
            base_embed = EmbeddingService().generate_embedding
        except Exception:  # noqa: BLE001 - each meaning search then says why it failed
            pass

    def soon(q, ars, df=None, dt=None, tag=""):
        if not meaning_ok or not ars:
            return None
        return pool.submit(_meaning, case_id, q, ars, embed_query=embed, collections=collections, phone=phone,
                           person=person, date_from=df, date_to=dt, tag=tag)
    def soon_phone(o):
        if not meaning_ok:
            return None
        return pool.submit(_meaning, case_id, without_name(question, o["name"]), ["phone_text"], embed_query=embed,
                           collections=collections, phone=o["extraction_id"], person=person,
                           tag=own_tag(o))
    f_undated = soon(question, undated, date_from, date_to)
    f_dated = soon(question, dated)
    f_phrasings = [soon(p, areas, tag=" (other phrasing)") for p in (understood.get("phrasings") or [])] if areas else []
    # messages on a named person's own phone, searched for the rest of the question (her name dropped): a message
    # there is about her without naming her (demo case: "You received $500.00 from Travis K." on Lena Marsh's phone
    # was not in the first 20 for "What payments did Lena Marsh receive?", 17 Nov)
    own = [o for o in (understood.get("own_phones") or []) if not phone and "phone_text" in areas]
    f_own = [soon_phone(o) for o in own] if own else []
    f_graph = pool.submit(_graph, case_id, question, understood.get("names") or [], understood.get("terms") or [],
                          embed_query=embed, expansions=understood.get("expansions") or [],
                          only_graph=tuple(kinds) == ("graph",)) if entities else None
    try:
        return _gather_lists(conn, case_id, question, understood, kinds, areas, only, dated, undated, phone, person,
                             date_from, date_to, embed, collections, meaning_ok, entities, notes, searched,
                             not_searched, clock, t0, f_undated, f_dated, f_phrasings, f_graph, exact,
                             own=list(zip(own, f_own)))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _gather_lists(conn, case_id, question, understood, kinds, areas, only, dated, undated, phone, person, date_from,
                  date_to, embed, collections, meaning_ok, entities, notes, searched, not_searched, clock, t0,
                  f_undated, f_dated, f_phrasings, f_graph, exact=False, own=()) -> dict[str, Any]:
    lists: list[list[dict]] = []
    meaning_all: list[dict] = []
    words_all: list[dict] = []
    message_word_hits = 0
    if areas:
        # the question itself: meaning and words; dated records inside the dates asked for, messages and passages not
        m, w, n = _embedded(conn, case_id, question, undated, embed_query=embed, collections=collections, phone=phone,
                            person=person, date_from=date_from, date_to=date_to, ready=f_undated,
                            meaning=f_undated is not None, exact=exact)
        m2, w2, n2 = _embedded(conn, case_id, question, dated, embed_query=embed, collections=collections,
                               phone=phone, person=person, ready=f_dated,
                               meaning=f_dated is not None, exact=exact) if dated else ([], [], [])
        meaning_all += m + m2
        words_all += w + w2
        for x in n + n2:
            if x not in notes:
                notes.append(x)
        if any(x.startswith("Meaning search unavailable") for x in n + n2):
            meaning_ok = False
        for f in f_phrasings:
            if f is not None:
                pm, _ = f.result()
                lists.append(pm)
        # every name tie (a person's numbers, accounts and other names) in one list, the ties taking turns: a list
        # each gave every row of a tied account a credit per tie (demo case, 17 Nov: 40 of a question's first 50
        # places were one account's ledger rows)
        tied: list[list[dict]] = []
        for e in understood.get("expansions") or []:
            _, ew, _ = _embedded(conn, case_id, '"%s"' % e["term"] if " " in e["term"] else e["term"], areas,
                                 embed_query=embed, collections=None, meaning=False, phone=phone, person=person,
                                 tag=" (name tie: %s)" % e["term"], exact=True)
            tied.append(ew)
        lists.append(_take_turns(tied))
        # phone messages holding words a message answering the question would hold (``message_words``, made by the
        # model from the question alone): one list of its own, beside the question's own words
        mw = understood.get("message_words") or []
        if mw and "phone_text" in areas:
            _, ww, _ = _embedded(conn, case_id, " ".join('"%s"' % x if " " in x else x for x in mw), ["phone_text"],
                                 embed_query=embed, collections=None, meaning=False, phone=phone, person=person,
                                 tag=" (message words)", exact=True)
            lists.append(ww)
            # each can climb past a candidate the search had without it, never more than one place each: the ranking
            # scores that many more, so every candidate it scored before is still scored
            message_word_hits = len(ww)
            searched.append("phone messages by words a message answering the question would hold, suggested by the "
                            "model from the question alone: %s" % ", ".join(mw))
        if own:
            lists.append(_own_phone_list(conn, case_id, question, own, person=person))
            searched += ["messages on %s as %s's own phone (%s; not confirmed by a person)" % (
                o["label"], o["name"], o["basis"]) for o, _ in own]
        searched += ["%s (%s)" % (k, "meaning and words" if meaning_ok else "words only") for k in kinds
                     if KIND_AREAS[k]]
    clock["embedded_areas"] = round(time.time() - t0, 2)
    t0 = time.time()
    doc_words = None
    if "documents" in kinds and (not only or "documents" in only):
        try:
            dw, doc_words = _documents_by_words(conn, case_id, question)
            # in the shared word list, counted as the embedded word search counts (question terms the passage holds)
            from services.phone import chat_retrieval
            qterms = chat_retrieval.terms(question)
            for h in dw:
                body = (h.get("text") or "").casefold()
                h["words"] = sum(1 for t in qterms if t in body) or 1
            words_all += dw
            searched.append("documents by their words")
        except Exception as exc:  # noqa: BLE001
            not_searched.append("documents by their words (%s)" % str(exc)[:120])
    clock["document_words"] = round(time.time() - t0, 2)
    t0 = time.time()
    if entities:
        gw, gm, gn = f_graph.result()
        meaning_all += gm
        words_all += gw
        notes += gn
        searched.append("graph entities by name, alias and meaning")
    clock["graph"] = round(time.time() - t0, 2)
    for k in KINDS:
        if k not in kinds:
            not_searched.append("%s (not asked for)" % k)
    lists = [_merge_meaning(meaning_all), _merge_words(words_all)] + lists
    return {"candidates": _rrf([l for l in lists if l]), "searched": searched, "not_searched": not_searched,
            "notes": notes, "meaning_search": meaning_ok, "documents_by_words": doc_words, "clock": clock,
            "message_word_hits": message_word_hits}
