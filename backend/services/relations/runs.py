"""Saving a group to look into, starting its analysis, and reading it back (lx-overlaps D).

``save_group`` stores a ``relation_query`` group in ``case_selections`` (members checked against the case). A group is
never rewritten: adding items to a running query saves a new group that holds the old members plus the new ones and
says in ``how.extends`` which group it grew from. ``start`` queues a run and works on it in a background thread that
writes its step and true counts to the row, so the page says what it is doing within two seconds and the run goes on
if the page is closed.
"""
from __future__ import annotations

import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from postgres.models.relation_run import RelationRun
from services import case_selections
from services.relations import engine
from services.relations.sources import DbSources

log = logging.getLogger(__name__)
WORDS = "Corroborate"
# A look compares every pair, so its work and its result grow with the square of the items: 400 items are 79,800 pairs.
MAX_ITEMS = 400
PAGE = 100


def normalise(db, case_id, members: list[dict]) -> list[dict]:
    """A marked passage becomes its document with the quote, as written from the stored text now (a passage that cannot
    be read is refused with the reason, never dropped). A photo becomes the phone records it belongs to
    (``services.corroborate.photos``)."""
    from services.corroborate import photos
    members = photos.expand(db, case_id, members)
    out = []
    for m in members:
        if m.get("type") != "evidence_passage":
            out.append(m)
            continue
        from services.evidence_page_text import PassageError, passage_anchor
        try:
            label, anchor = passage_anchor(db, case_id, str(m["id"]))
        except PassageError as exc:
            raise case_selections.SelectionError(str(exc)) from exc
        out.append({"type": "evidence", "id": str(m["id"]).split(":")[0], "label": label,
                    "quote": str((anchor or {}).get("quote") or "")})
    return out


def _question(raw: dict) -> dict:
    """The question as the person left it: its kind and the chips (when, nights, who, what, compare with), as text,
    and the chips Corroborate's engine reads, each checked for its form: ``people`` and ``against`` (person keys: the group asked about and the group compared with), ``person`` (the
    one asked about), ``hours`` (start "HH:MM" and length in hours), ``after`` (a date) and ``compare_with`` (a
    comparison set the engine knows)."""
    from services.corroborate import model as corroborate_model
    chips = raw.get("chips") if isinstance(raw.get("chips"), dict) else {}
    out = {k: str(v)[:300] for k, v in chips.items() if k in ("when", "nights", "who", "what", "compare_with", "scope", "claim_id")}
    if isinstance(chips.get("people"), list):
        out["people"] = [str(k)[:200] for k in chips["people"][:50]]
    if isinstance(chips.get("against"), list):
        out["against"] = [str(k)[:200] for k in chips["against"][:50]]
    if isinstance(chips.get("person"), str):
        out["person"] = chips["person"][:200]
    hours = chips.get("hours")
    if isinstance(hours, dict) and re.fullmatch(r"\d{2}:\d{2}", str(hours.get("start") or "")):
        try:
            length = float(hours.get("length_h"))
        except (TypeError, ValueError):
            length = 0
        if 0 < length <= 48:
            out["hours"] = {"start": hours["start"], "length_h": length}
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(chips.get("after") or "")):
        out["after"] = chips["after"]
    if "compare_with" in out and out["compare_with"] not in corroborate_model.COMPARISON_KINDS:
        out["compare_words"] = out.pop("compare_with")  # the words a person reads; the engine picks the set
    return {"kind": str(raw.get("kind") or "")[:40], "text": str(raw.get("text") or "")[:500], "chips": out}


def save_group(db, *, case_id, members: list[dict], user=None, extends: str | None = None, surface: str = "relation",
               question: dict | None = None) -> dict:
    """Save the group. ``extends`` is a group of this case whose members are kept and added to. ``question`` (a
    Corroborate question: kind and chips) is kept with how the group was chosen, so every run of it asks it."""
    held: list[dict] = []
    if extends:
        base = case_selections.describe(db, case_id, extends, member_limit=10**9)
        if base is None or base["group_type"] != "relation_query":
            raise case_selections.SelectionError("The query to add to is not in this case.")
        held = [{k: v for k, v in m.items() if k in ("type", "id", "label", "quote")} for m in base["members"]]
    chosen = held + normalise(db, case_id, list(members))
    if len(chosen) > MAX_ITEMS:
        units, folded = pair_units(db, case_id, chosen)
        if len(units) > MAX_ITEMS:
            pairs = len(units) * (len(units) - 1) // 2
            more = (f" (positions of one phone in one place count as one: {len(chosen):,} items are {len(units):,})"
                    if folded else "")
            raise case_selections.SelectionError(
                f"{len(units):,} items make {pairs:,} pairs to compare{more}, more than one look can read "
                f"({MAX_ITEMS} items). Choose fewer items or look at a narrower range. Nothing was saved.")
    return case_selections.freeze(db, case_id=case_id, group_type="relation_query", members=chosen,
                                  how={"surface": surface, **({"extends": extends} if extends else {}),
                                       **({"question": _question(question)} if question else {})},
                                  words=WORDS, user=user)


FOLD_JOIN_M = 500.0  # a phone's position within this distance of the first position of its place joins that place


def pair_units(db, case_id, members: list[dict]) -> tuple[list[dict], list[dict]]:
    """The members the pair step compares. A group over ``MAX_ITEMS`` (a Map area brings in every position there)
    has the presence positions of each phone in each place made one place member (its centre, and a radius reaching
    its furthest position), so 475 positions of 5 phones are 5 places, not 475 items and 112,575 pairs. Corroborate
    still weighs every position. Returns the members and, per place made, its phone, label and the positions it
    holds. A group within the limit is returned as it is."""
    if len(members) <= MAX_ITEMS:
        return members, []
    from sqlalchemy import text
    ids = [str(m["id"]) for m in members if m.get("type") == "phone_record"]
    rows = db.execute(text(
        "SELECT DISTINCT ON (record_uid) CAST(record_uid AS text), CAST(extraction_id AS text), lat, lon "
        "FROM pol_place_observation WHERE case_id = :c AND kind = 'presence' AND lat IS NOT NULL AND lon IS NOT NULL "
        "AND CAST(record_uid AS text) = ANY(:ids) ORDER BY record_uid, start_utc"),
        {"c": str(case_id), "ids": ids}).fetchall() if ids else []
    pos = {r[0]: (r[1], float(r[2]), float(r[3])) for r in rows}
    try:
        from services.phone.readings import phone_labels
        labels = phone_labels(db.connection(), str(case_id)) if pos else {}
    except Exception:  # noqa: BLE001 - without labels the place says "one phone"
        labels = {}
    return fold_units(members, pos, labels)


def fold_units(members: list[dict], pos: dict[str, tuple[str, float, float]], labels: dict[str, str]):
    """``pos``: record id -> (phone, lat, lon) of each presence position among the members."""
    from services.corroborate import model as M
    groups: dict[str, list[list[tuple[str, float, float]]]] = {}
    for uid, (phone, lat, lon) in sorted(pos.items(), key=lambda x: (x[1][1], x[1][2])):
        places = groups.setdefault(phone, [])
        home = next((g for g in places if M.haversine_m(g[0][1], g[0][2], lat, lon) <= FOLD_JOIN_M), None)
        if home is None:
            places.append([(uid, lat, lon)])
        else:
            home.append((uid, lat, lon))
    folded, place_of = [], {}
    for phone, places in groups.items():
        for g in places:
            if len(g) < 2:
                continue
            lat = sum(x[1] for x in g) / len(g)
            lon = sum(x[2] for x in g) / len(g)
            radius = max([50.0] + [M.haversine_m(lat, lon, x[1], x[2]) for x in g])
            label = f"{len(g):,} positions of {labels.get(phone) or 'one phone'}"
            member = {"type": "place", "id": f"{lat:.6f},{lon:.6f},{radius:.0f},{phone}", "label": label}
            folded.append({"phone": phone, "label": label, "positions": len(g), "member": member,
                           "refs": [f"phone_record:{x[0]}" for x in g]})
            for x in g:
                place_of[x[0]] = member
    if not folded:
        return members, []
    out, seen = [], set()
    for m in members:
        target = place_of.get(str(m["id"])) if m.get("type") == "phone_record" else None
        if target is None:
            out.append(m)
        elif target["id"] not in seen:
            seen.add(target["id"])
            out.append(target)
    return out, folded


def start(db, *, case_id, selection_id, user=None, session_factory=None, inline: bool = False) -> dict:
    sel = case_selections.describe(db, case_id, selection_id, member_limit=10**9)
    if sel is None or sel["group_type"] != "relation_query":
        raise case_selections.SelectionError("That query is not in this case.")
    row = RelationRun(id=uuid.uuid4(), case_id=uuid.UUID(str(case_id)), selection_id=uuid.UUID(str(selection_id)),
                      status="queued", step="Waiting to start", progress={"items": sel["member_count"]},
                      requested_by=getattr(user, "id", None))
    db.add(row)
    db.commit()
    run_id = str(row.id)
    if inline:
        work(run_id, str(case_id), session_factory=lambda: db)
    else:
        if session_factory is None:
            from postgres.session import _get_background_session_local
            session_factory = _get_background_session_local()
        threading.Thread(target=work, args=(run_id, str(case_id)), kwargs={"session_factory": session_factory},
                         daemon=True, name=f"relations-{run_id[:8]}").start()
    return view(db, case_id, run_id)


def work(run_id: str, case_id: str, *, session_factory) -> None:
    session = session_factory()
    own = session is not None and session_factory is not None
    try:
        row = session.get(RelationRun, uuid.UUID(run_id))
        sel = case_selections.describe(session, case_id, str(row.selection_id), member_limit=10**9)
        members = [{k: v for k, v in m.items() if k in ("type", "id", "label", "quote")} for m in sel["members"]]
        row.status = "running"
        row.step = f"Reading {len(members):,} items"
        session.commit()

        def progress(step, done, total):
            row.step = f"{step} ({done:,} of {total:,})"
            session.commit()
        corroboration = None
        if "question" in (sel.get("how") or {}):
            # Corroborate first: its level is what the page shows, so it lands before the slower link analysis
            from services.corroborate import engine as corroborate
            from services.corroborate.store import CaseStore
            corroboration = corroborate.run(CaseStore(session, case_id), members, sel["how"]["question"], progress)
            row.result = {"corroboration": corroboration, "partial": True}
            row.progress = {**(row.progress or {}), "level": corroboration["level"]["name"]}
            session.commit()
            _save_lead(session, case_id, row, members, corroboration)
        if corroboration is not None and corroboration.get("claim"):
            # a claim is weighed against the phones only; there are no records to pair
            row.result = claim_only_result(corroboration, len(members))
            row.status, row.step, row.finished_at = "done", "Done", datetime.now(timezone.utc)
            row.progress = {"items": len(members), "level": corroboration["level"]["name"]}
            session.commit()
            return
        link_members, folded = pair_units(session, case_id, members)
        result = engine.run(DbSources(session, case_id), link_members, progress)
        if folded:
            result["folded"] = {
                "says": (f"{sum(f['positions'] for f in folded):,} positions of {len({f['phone'] for f in folded})} "
                         f"phone{'' if len({f['phone'] for f in folded}) == 1 else 's'} are compared as "
                         f"{len(folded)} place{'' if len(folded) == 1 else 's'}: positions of one phone in one place "
                         f"count as one item here. The group holds {len(members):,} items."),
                "places": [{"label": f["label"], "ref": f"place:{f['member']['id']}", "positions": f["positions"],
                            "records": f["refs"]} for f in folded]}
        if corroboration is not None:
            result["corroboration"] = corroboration
        row.result, row.status, row.step = result, "done", "Done"
        row.progress = {"items": len(members), **({"compared": result["counts"]["items"]} if folded else {}), "candidates": result["counts"]["candidates"],
                        "no_links": result["counts"]["no_links"],
                        **({"level": corroboration["level"]["name"]} if corroboration is not None else {})}
        row.finished_at = datetime.now(timezone.utc)
        session.commit()
    except Exception as exc:  # noqa: BLE001 - the run fails visibly, with the reason
        log.exception("relation run %s failed", run_id)
        session.rollback()
        row = session.get(RelationRun, uuid.UUID(run_id))
        if row is not None:
            row.status, row.error, row.step = "failed", f"{type(exc).__name__}: {exc}"[:2000], "Stopped"
            row.finished_at = datetime.now(timezone.utc)
            session.commit()
    finally:
        # a sessionmaker has no __name__: reading it raised here, after the run was saved, and the session stayed open
        if own and getattr(session, "bind", None) is not None and getattr(session_factory, "__name__", "") != "<lambda>":
            session.close()


def _save_lead(session, case_id, row, members, corroboration) -> None:
    """Each answer saves to Leads as asked by the person who asked (lx-leads C). A failure to save the lead is logged
    and leaves the run as it is: the answer is still shown."""
    from types import SimpleNamespace
    from services.leads import store as leads
    try:
        leads.save_asked(session, case_id, selection_id=row.selection_id, run_id=row.id, result=corroboration,
                         members=members, user=SimpleNamespace(id=row.requested_by))
    except Exception:  # noqa: BLE001 - logged; the run's answer stands
        log.exception("saving run %s as a lead failed", row.id)
        session.rollback()


def view(db, case_id, run_id, *, with_result: bool = True) -> dict[str, Any]:
    row = db.get(RelationRun, uuid.UUID(str(run_id)))
    if row is None or str(row.case_id) != str(case_id):
        raise LookupError("That run is not in this case.")
    out = {"id": str(row.id), "selection_id": str(row.selection_id), "status": row.status, "step": row.step,
           "progress": row.progress or {}, "error": row.error, "hypotheses": row.hypotheses,
           "created_at": row.created_at.isoformat() if row.created_at else None,
           "finished_at": row.finished_at.isoformat() if row.finished_at else None}
    if with_result:
        out["result"] = _first_page(row.result)
    return out


def claim_only_result(corroboration: dict, n_members: int) -> dict:
    """A claim's run has no link analysis; its result carries the keys every reader of a run result expects, empty."""
    return {"corroboration": corroboration, "claim_only": True, "items": [], "candidates": [], "no_links": [],
            "analyses": [], "out_of_reach": [], "counts": {"items": n_members, "candidates": 0, "no_links": 0}}


def _first_page(result: dict | None) -> dict | None:
    """The result with the first ``PAGE`` candidates and pairs with no link; ``paging`` says how many of how many, and
    ``rows`` reads the rest. Counts, items and analyses are always whole."""
    if not result:
        return result
    out = dict(result)
    out["paging"] = {"candidates": {"total": len(result["candidates"]), "shown": min(PAGE, len(result["candidates"]))},
                     "no_links": {"total": len(result["no_links"]), "shown": min(PAGE, len(result["no_links"]))}, "page": PAGE}
    out["candidates"] = result["candidates"][:PAGE]
    out["no_links"] = result["no_links"][:PAGE]
    return out


def rows(db, case_id, run_id, section: str, offset: int = 0, limit: int = PAGE) -> dict[str, Any]:
    """More candidates or pairs with no link, in the order the run ranked them."""
    if section not in ("candidates", "no_links"):
        raise ValueError("Read candidates or no_links.")
    row = db.get(RelationRun, uuid.UUID(str(run_id)))
    if row is None or str(row.case_id) != str(case_id) or not row.result:
        raise LookupError("That run is not in this case.")
    everything = row.result[section]
    page = everything[max(0, offset):max(0, offset) + max(1, min(limit, 500))]
    return {"section": section, "total": len(everything), "offset": max(0, offset), "returned": len(page),
            "next_offset": offset + len(page) if offset + len(page) < len(everything) else None, "rows": page}


def full_result(db, case_id, run_id) -> dict | None:
    row = db.get(RelationRun, uuid.UUID(str(run_id)))
    return row.result if row is not None and str(row.case_id) == str(case_id) else None


def latest_for(db, case_id, selection_id) -> str | None:
    return db.scalar(select(RelationRun.id).where(RelationRun.case_id == uuid.UUID(str(case_id)),
                                                  RelationRun.selection_id == uuid.UUID(str(selection_id)))
                     .order_by(RelationRun.created_at.desc()).limit(1))
