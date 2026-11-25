"""Where Corroborate reads the case (lx-corroengine B). Read-only; every query is scoped to the case.

``CaseStore`` turns the case into the plain people and records of ``model``. Tests give the engine a fake with the
same methods. It reuses what Loupe already holds and never recomputes it: the phone owner records, the dossiers'
recorded numbers, the presence reading of positions (``pol_place_observation``: a received photo is never presence),
the phones' full activity streams (``pol_activity_event``), the ledger as admitted (superseded rows left out), the
documents' extracted text, and the phones' labels.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from services.corroborate import model as M

_STAMP = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})")
_AMOUNT = re.compile(r"\$\s?([\d,]+\.\d{2})")


def _uid(v) -> str | None:
    try:
        return str(uuid.UUID(str(v)))
    except (ValueError, TypeError):
        return None


class CaseStore:
    def __init__(self, db, case_id):
        self.db, self.case = db, str(case_id)
        self.c = {"c": self.case}
        self._people: list[dict] | None = None
        self._zone: str | None = None
        self._phone_days: dict[str, tuple[list, int]] = {}
        self.set_aside: dict[str, int] = {}  # phone -> record days set aside from its coverage (``M.phone_spans``)

    def q(self, sql: str, **params):
        return self.db.execute(text(sql), {**self.c, **params})

    # -- the case's zone -----------------------------------------------------------------------------------------
    def zone(self) -> str:
        """The zone times of day are read in: the display zone most of the case's phones were examined in. Every
        record is stored as its instant, so this only names hours; it never moves a record."""
        if self._zone is None:
            zones = Counter()
            for (flags,) in self.q("SELECT flags FROM phone_extractions WHERE case_id = :c AND standing = 'active'"):
                z = ((flags or {}).get("examiner_selected_zone") or {}).get("zone")
                if z:
                    zones[z] += 1
            self._zone = zones.most_common(1)[0][0] if zones else "UTC"
        return self._zone

    def phone_zones(self) -> dict[str, str | None]:
        out = {}
        for e, flags, dz in self.q("SELECT id, flags, device_zone FROM phone_extractions WHERE case_id = :c AND "
                                   "standing = 'active'"):
            out[str(e)] = dz or ((flags or {}).get("examiner_selected_zone") or {}).get("zone")
        return out

    # -- people --------------------------------------------------------------------------------------------------
    def people(self) -> list[dict]:
        """Everyone the case knows: each dossier with its recorded numbers and e-mails, each phone's owner, and the
        bank accounts whose holder is a dossier's name. A phone joins a dossier when the dossier records the phone's
        owner number; that join and an account's are Loupe's suggestions, labelled so."""
        if self._people is not None:
            return self._people
        from services.phone.readings import phone_labels
        labels = phone_labels(self.db.connection(), self.case)
        people: dict[str, dict] = {}
        for pid, name, contacts in self.q(
                "SELECT id, display_name, contacts FROM case_profiles WHERE case_id = :c AND archived_at IS NULL "
                "AND status = 'active'"):
            p = people.setdefault(f"person:{pid}", {"key": f"person:{pid}", "label": name, "dossier_id": str(pid),
                                                    "numbers": set(), "handles": set(), "emails": set(),
                                                    "accounts": [], "phones": [], "names": [name], "links": []})
            for ct in contacts or []:
                v = str(ct.get("value") or "")
                if ct.get("kind") == "phone" and M.norm_number(v):
                    p["numbers"].add(M.norm_number(v))
                    p["links"].append({"identifier": v, "how": "recorded", "basis": "on the dossier"})
                elif ct.get("kind") == "email" and "@" in v:
                    p["emails"].add(v.lower())
                    p["links"].append({"identifier": v, "how": "recorded", "basis": "on the dossier"})
        owners: dict[str, set] = defaultdict(set)
        for ext, raw in self.q(
                "SELECT DISTINCT p.extraction_id, p.identifier_raw FROM phone_participations p JOIN phone_extractions e "
                "ON e.id = p.extraction_id AND e.standing = 'active' WHERE p.case_id = :c AND p.is_phone_owner AND "
                "p.identifier_raw IS NOT NULL"):
            owners[str(ext)].add(str(raw))
        for ext in labels:
            if ext not in owners:
                continue
            vals = owners[ext]
            nums = {M.norm_number(v.split("@")[0]) for v in vals if "@" not in v or v.endswith("whatsapp.net")}
            nums.discard(None)
            handles = {v.lower() for v in vals if v.startswith("@")}
            emails = {v.lower() for v in vals if "@" in v and not v.startswith("@") and not v.endswith("whatsapp.net")}
            match = [p for p in people.values() if p["numbers"] & nums]
            if len(match) == 1:
                p = match[0]
                p["links"].append({"identifier": labels[ext], "how": "suggested",
                                   "basis": "the phone's owner number is recorded on the dossier"})
            else:
                shown = sorted(nums)[0] if nums else ext[:8]
                key = f"phone:{ext}"
                p = people.setdefault(key, {"key": key, "label": f"the user of {labels[ext]} (+{shown})",
                                            "dossier_id": None, "numbers": set(), "handles": set(), "emails": set(),
                                            "accounts": [], "phones": [], "names": [], "links": []})
            p["phones"].append(ext)
            p.setdefault("phone_labels", {})[ext] = labels[ext]
            for n in sorted(nums - p["numbers"]):
                p["links"].append({"identifier": "+" + n, "how": "suggested", "basis": f"owner number of {labels[ext]}"})
            for h in sorted(handles - p["handles"]):
                p["links"].append({"identifier": h, "how": "suggested", "basis": f"owner handle of {labels[ext]}"})
            p["numbers"] |= nums
            p["handles"] |= handles
            p["emails"] |= emails
        for acc, holder, inst, ident in self.q(
                "SELECT id, holder_name, institution_name, identifier_as_printed FROM financial_accounts WHERE case_id = :c"):
            hits = [p for p in people.values() if holder and any(M.names_match(n, holder) for n in p["names"] if n)]
            if len(hits) == 1:
                hits[0]["accounts"].append(str(acc))
                hits[0]["links"].append({"identifier": f"{inst} {ident}", "how": "suggested",
                                         "basis": f"account holder printed as “{holder}”"})
        self._people = list(people.values())
        return self._people

    # -- the selection -------------------------------------------------------------------------------------------
    def selection_points(self, members: list[dict]) -> tuple[list[dict], list[dict]]:
        """Each member as a dated point with the people it names, and the members that could not be read (with why)."""
        people = self.people()
        by_phone = {e: p["key"] for p in people for e in p["phones"]}
        by_account = {a: p["key"] for p in people for a in p["accounts"]}
        points, unread = [], []
        for m in members:
            t, mid = m.get("type"), str(m.get("id"))
            ref = f"{t}:{mid}"
            pt = {"ref": ref, "type": t, "people": [], "label": m.get("label") or ref}
            if t == "phone_record" and _uid(mid):
                row = self.q(
                    "SELECT extraction_id, COALESCE(sort_instant, NULL), kind, app FROM phone_comm_events WHERE case_id = :c "
                    "AND record_uid = :u ORDER BY sort_instant NULLS LAST LIMIT 1", u=mid).first()
                pos = None if row else self.q(
                    "SELECT extraction_id, start_utc, lat, lon, radius_m, kind FROM pol_place_observation WHERE "
                    "case_id = :c AND record_uid = :u ORDER BY start_utc LIMIT 1", u=mid).first()
                act = None if (row or pos) else self.q(
                    "SELECT extraction_id, instant_utc FROM pol_activity_event WHERE case_id = :c AND record_uid = :u "
                    "ORDER BY instant_utc LIMIT 1", u=mid).first()
                if row:
                    pt.update(phone=str(row[0]), at=M.as_utc(row[1]), kind=row[2], app=row[3])
                    pt["people"] = [by_phone.get(str(row[0]))] + self._record_parties(mid, people)
                elif pos:
                    pt.update(phone=str(pos[0]), at=M.as_utc(pos[1]), kind="position" if pos[5] == "presence" else
                              "media_position", place={"lat": pos[2], "lon": pos[3], "radius_m": pos[4]})
                    pt["people"] = [by_phone.get(str(pos[0]))]
                elif act:
                    pt.update(phone=str(act[0]), at=M.as_utc(act[1]), kind="activity")
                    pt["people"] = [by_phone.get(str(act[0]))]
                else:
                    unread.append({"ref": ref, "why": "No dated phone record with this id in the case."})
                    continue
                note = self._notification(mid)
                if note:
                    pt.update(note)
            elif t == "financial_transaction" and _uid(mid):
                row = self.q("SELECT account_id, COALESCE(transaction_date, posted_date), amount_minor, direction, "
                             "COALESCE(counterparty_raw, '') || ' ' || COALESCE(description, '') FROM financial_transactions "
                             "WHERE case_id = :c AND id = :i", i=mid).first()
                if not row or not row[1]:
                    unread.append({"ref": ref, "why": "The payment has no date, or is not in this case."})
                    continue
                payer, payee = self._payment_parties(by_account.get(str(row[0])), row[3], row[4], people)
                pt.update(at=M.as_utc(row[1]), day_only=True, kind="payment", amount_minor=row[2],
                          direction=row[3], memo=" ".join(str(row[4] or "").split()))
                pt["people"] = [payer, payee]
            elif t == "document_row":
                fid, _, idx = mid.partition(":")
                rows = self.document_rows(fid) if _uid(fid) else []
                hit = next((r for r in rows if r["index"] == int(idx or -1)), None) if idx.isdigit() else None
                if not hit:
                    unread.append({"ref": ref, "why": "That row of the document could not be read."})
                    continue
                pt.update(at=hit["at"], kind="doc_row", people=hit["parties"], label=hit["text"])
            elif t == "evidence" and m.get("quote"):
                stamp = _STAMP.search(str(m["quote"]))
                if not stamp:
                    unread.append({"ref": ref, "why": "The marked passage holds no date and time."})
                    continue
                at = self._local_to_utc(stamp.group(1), stamp.group(2))
                pt.update(at=at, kind="doc_row", people=[p["key"] for p in people if any(
                    M.names_match(n, str(m["quote"])) for n in p["names"] if n)])
            elif t == "person":
                key = f"person:{mid}"
                if key not in {p["key"] for p in people}:
                    unread.append({"ref": ref, "why": "No such person in this case."})
                    continue
                pt.update(kind="person", people=[key])
            elif t == "phone":
                if mid not in by_phone:
                    unread.append({"ref": ref, "why": "No such phone in this case."})
                    continue
                pt.update(kind="phone", phone=mid, people=[by_phone[mid]])
            elif t == "place":
                try:
                    lat, lon, radius = (float(x) for x in mid.split(","))
                except ValueError:
                    unread.append({"ref": ref, "why": "A place is lat,lon,radius."})
                    continue
                pt.update(kind="place", place={"lat": lat, "lon": lon, "radius_m": radius})
            elif t in ("graph_entity", "financial_party", "entry", "timeline_event", "evidence", "financial_account"):
                label = str(m.get("label") or "")
                if t == "financial_account" and mid in by_account:
                    pt.update(kind="account", people=[by_account[mid]])
                else:
                    named = [p["key"] for p in people if any(M.names_match(n, label) for n in p["names"] if n)]
                    num = M.norm_number(label)
                    named += [p["key"] for p in people if num and num in p["numbers"]]
                    if not named:
                        unread.append({"ref": ref, "why": "Names no person or number Loupe can join to the records."})
                        continue
                    pt.update(kind="named", people=list(dict.fromkeys(named)))
            else:
                unread.append({"ref": ref, "why": "This kind of item is not read by Corroborate yet."})
                continue
            pt["people"] = [p for p in dict.fromkeys(pt.get("people") or []) if p]
            points.append(pt)
        return points, unread

    def _notification(self, uid) -> dict | None:
        row = self.q("SELECT t.value FROM pv_text t JOIN pv_record r ON r.record_uid = t.record_uid WHERE "
                     "r.case_id = :c AND r.record_uid = :u AND r.model_type = 'Notification' AND t.field_path = 'Body' "
                     "LIMIT 1", u=uid).first()
        if row and _AMOUNT.search(row[0] or ""):
            return {"kind": "payment_alert", "body": row[0]}
        return None

    def place_points(self, place: dict, phones: list[str] | None) -> list[dict]:
        """Presence positions inside a chosen area (all phones, or the people's phones), each as a dated point."""
        r = place["radius_m"]
        dlat = r / 111_000.0
        from math import cos, radians
        dlon = r / (111_000.0 * max(0.2, abs(cos(radians(place["lat"])))))
        rows = self.q(
            "SELECT record_uid, extraction_id, start_utc, lat, lon, radius_m FROM pol_place_observation WHERE "
            "case_id = :c AND kind = 'presence' AND lat BETWEEN :a AND :b AND lon BETWEEN :x AND :y "
            "AND (CAST(:e AS uuid[]) IS NULL OR extraction_id = ANY(CAST(:e AS uuid[])))",
            a=place["lat"] - dlat, b=place["lat"] + dlat, x=place["lon"] - dlon, y=place["lon"] + dlon,
            e=phones).fetchall()
        return [{"ref": f"phone_record:{u}", "type": "phone_record", "phone": str(e), "at": M.as_utc(t),
                 "kind": "position", "place": {"lat": la, "lon": lo, "radius_m": rad}}
                for u, e, t, la, lo, rad in rows if M.haversine_m(place["lat"], place["lon"], la, lo) <= r]

    def _record_parties(self, uid, people) -> list[str]:
        out = []
        for (raw,) in self.q("SELECT identifier_raw FROM phone_participations WHERE case_id = :c AND record_uid = :u "
                             "AND NOT COALESCE(is_phone_owner, false)", u=uid):
            k = M.person_for_value(people, raw)
            if k:
                out.append(k)
        return out

    def _payment_parties(self, holder, direction, words, people):
        named = M.person_for_name([p for p in people if p["key"] != holder], words or "")
        if direction == "credit":
            return named, holder
        return holder, named

    def _local_to_utc(self, day: str, hm: str) -> datetime:
        zone = M.tz(self.zone())
        local = datetime.fromisoformat(f"{day}T{hm}").replace(tzinfo=zone)
        return local.astimezone(timezone.utc)

    # -- documents -----------------------------------------------------------------------------------------------
    def document_rows(self, file_id: str) -> list[dict]:
        """Dated rows of one document's extracted text: each line or table row holding a date and time, with the
        people it names (full names only). Times without a zone are read in the case's zone, which is stated."""
        row = self.q("SELECT f.original_filename, t.content FROM evidence_document_texts t JOIN evidence_files f ON "
                     "f.id = t.evidence_file_id WHERE f.case_id = :c AND f.id = :f AND f.deleted_at IS NULL",
                     f=file_id).first()
        if not row:
            return []
        name, content = row
        people = self.people()
        chunks = _document_chunks(content or "")
        out = []
        for i, chunk in enumerate(chunks):
            stamp = _STAMP.search(chunk)
            if not stamp:
                continue
            words = re.sub(r"[\"\[\]{}]", " ", chunk)
            words = re.sub(r"\s+", " ", words).strip()
            parties = [p["key"] for p in people if any(M.names_match(n, words) for n in p["names"] if n)]
            out.append({"index": i, "at": self._local_to_utc(stamp.group(1), stamp.group(2)), "text": words[:300],
                        "parties": parties, "source": file_id, "source_label": name})
        return out

    def dated_documents(self, people: list[dict], windows: list[tuple[datetime, datetime]]) -> list[dict]:
        """Records for documents that name one of the people and state a date of their own (written, signed or
        received), read from the text by Loupe or corrected by a person. The day is the document's; the body says
        so, and says "read by Loupe, not confirmed" until a person confirms the date. Time-of-day is unknown."""
        from services import document_date_store as D
        ids = self.documents_naming(people, need_time=False)
        if not ids or not windows:
            return []
        out = []
        for v in D.effective(self.db, self.case, ids, confirmed_only=getattr(self, "confirmed_dates_only", False)):
            if v["kind"] == "period":
                continue
            day = M.as_utc(datetime.fromisoformat(v["date_from"]))
            if not any(lo_ <= day <= hi_ or lo_.date() <= day.date() <= hi_.date() for lo_, hi_ in windows):
                continue
            row = self.q("SELECT f.original_filename, t.content FROM evidence_document_texts t JOIN evidence_files f ON "
                         "f.id = t.evidence_file_id WHERE f.id = :f", f=v["evidence_file_id"]).first()
            if not row:
                continue
            name, content = row
            words = re.sub(r"\s+", " ", content or "")
            parties = [p["key"] for p in people if any(M.names_match(n, words) for n in p["names"] if n)]
            who = v["label"] or f"confirmed by {v['confirmed_by'] or 'a person'}"
            out.append({"ref": f"document_date:{v['id']}", "kind": "doc_row", "at": day, "day_only": True, "parties": parties,
                        "body": f"Document {v['kind']} {v['date_from']} ({who}): {v['words']}"[:300],
                        "source": v["evidence_file_id"], "source_label": name, "read_date": True})
        return out

    def documents_naming(self, people: list[dict], need_time: bool = True) -> list[str]:
        """Documents whose text names one of the people in full (surname search first, then the full-name check).
        ``need_time`` keeps only documents with a dated and timed line, as the document rows need."""
        surnames = sorted({M.name_words(n)[-1] for p in people for n in p["names"] if n and len(M.name_words(n)) >= 2})
        if not surnames:
            return []
        ids = []
        for fid, content in self.q(
                "SELECT f.id, t.content FROM evidence_document_texts t JOIN evidence_files f ON f.id = t.evidence_file_id "
                "WHERE f.case_id = :c AND f.deleted_at IS NULL AND t.content ~* :rx",
                rx="(" + "|".join(re.escape(s) for s in surnames) + ")"):
            if (not need_time or _STAMP.search(content or "")) and any(M.names_match(n, content) for p in people for n in p["names"] if n):
                ids.append(str(fid))
        return ids

    # -- records -------------------------------------------------------------------------------------------------
    def records(self, people: list[dict], windows: list[tuple[datetime, datetime]], everyone: list[dict]) -> list[dict]:
        """The people's messages, calls, e-mails, positions, payments, payment alerts and document rows inside the
        windows. ``everyone`` resolves the other end of a record to a person."""
        if not windows:
            return []
        recs = self.phone_records(people, windows, everyone)
        accounts = {a: p["key"] for p in everyone for a in p["accounts"]}
        lo, hi = min(w[0] for w in windows), max(w[1] for w in windows) + M.MONEY_SPREAD
        names = [n for p in people for n in p["names"] if n]
        for tid, acc, day, amount, direction, words, desc in self.q(
                "SELECT id, account_id, COALESCE(transaction_date, posted_date), amount_minor, direction, "
                "COALESCE(counterparty_raw, '') || ' ' || COALESCE(description, ''), description FROM financial_transactions "
                "WHERE case_id = :c AND superseded_by_id IS NULL AND COALESCE(transaction_date, posted_date) BETWEEN "
                ":lo AND :hi", lo=lo.date(), hi=hi.date()):
            holder = accounts.get(str(acc))
            if holder not in {p["key"] for p in people} and not any(M.names_match(n, words) for n in names):
                continue
            payer, payee = self._payment_parties(holder, direction, words, everyone)
            cash = "cash deposit" in (desc or "").casefold() and direction == "credit"
            if cash:
                payer, payee = holder, None
            recs.append({"ref": f"financial_transaction:{tid}", "kind": "payment", "at": M.as_utc(day), "day_only": True,
                         "owner": payer, "parties": [payee] if payee else [], "amount_minor": amount, "body": words.strip(),
                         "cash_deposit": cash,
                         "dup_key": ("pay", payer, (payee,) if payee else (), abs(amount or 0), day)})
        for fid in self.documents_naming(people):
            for r in self.document_rows(fid):
                if any(lo_ <= r["at"] <= hi_ for lo_, hi_ in windows):
                    recs.append({"ref": f"document_row:{fid}:{r['index']}", "kind": "doc_row", "at": r["at"],
                                 "parties": r["parties"], "body": r["text"], "source": fid,
                                 "source_label": r["source_label"]})
        recs.extend(self.dated_documents(people, windows))
        return recs

    def phone_records(self, people: list[dict], windows: list[tuple[datetime, datetime]],
                      everyone: list[dict]) -> list[dict]:
        """The people's phone records in the windows: messages, calls, e-mails, positions and payment alerts (an alert
        up to three days after a window's end). Every one has a time and a ``phone_record:`` ref."""
        phones = [e for p in people for e in p["phones"]]
        owner = {e: p["key"] for p in everyone for e in p["phones"]}
        recs: list[dict] = []
        rng = ", ".join(f"(CAST(:lo{i} AS timestamptz), CAST(:hi{i} AS timestamptz))" for i in range(len(windows)))
        wp = {f"lo{i}": lo for i, (lo, _) in enumerate(windows)} | {f"hi{i}": hi for i, (_, hi) in enumerate(windows)}
        if phones:
            parts = defaultdict(list)
            for uid, raw, role in self.db.execute(text(
                    f"WITH w(lo, hi) AS (VALUES {rng}) SELECT p.record_uid, p.identifier_raw, p.role FROM "
                    "phone_participations p JOIN phone_comm_events c ON c.record_uid = p.record_uid AND c.case_id = p.case_id "
                    "JOIN w ON c.sort_instant BETWEEN w.lo AND w.hi WHERE p.case_id = :c AND "
                    "c.extraction_id = ANY(CAST(:e AS uuid[])) AND NOT COALESCE(p.is_phone_owner, false)"),
                    {**self.c, **wp, "e": phones}):
                parts[str(uid)].append((raw, role))
            seen = set()
            for ext, uid, kind, at, body, direction, thread, app, deleted in self.db.execute(text(
                    f"WITH w(lo, hi) AS (VALUES {rng}) SELECT DISTINCT c.extraction_id, c.record_uid, c.kind, c.sort_instant, "
                    "c.body, c.direction, c.thread_key, c.app, c.deleted_state FROM phone_comm_events c JOIN w ON "
                    "c.sort_instant BETWEEN w.lo AND w.hi WHERE c.case_id = :c AND c.extraction_id = ANY(CAST(:e AS uuid[]))"),
                    {**self.c, **wp, "e": phones}):
                if uid in seen:
                    continue
                seen.add(uid)
                o = owner.get(str(ext))
                vals = [r for r, _ in parts.get(str(uid), []) if r]
                ps = [k for k in (M.person_for_value(everyone, v) for v in vals) if k and k != o]
                sender = o if direction == "outgoing" else next(
                    (M.person_for_value(everyone, r) for r, role in parts.get(str(uid), []) if role in ("sender", "caller")), None)
                at = M.as_utc(at)
                recs.append({"ref": f"phone_record:{uid}", "kind": kind, "at": at, "phone": str(ext), "owner": o,
                             "parties": list(dict.fromkeys(ps)), "counterpart_values": [_norm_value(v) for v in vals],
                             "thread": thread, "app": app, "body": body, "sender": sender,
                             "deleted": bool(deleted and deleted.lower() != "intact"),
                             "dup_key": contact_dup_key(kind, at, body, [o] + ps)})
            for ext, uid, at, lat, lon, rad, kind, src in self.db.execute(text(
                    f"WITH w(lo, hi) AS (VALUES {rng}) SELECT DISTINCT o.extraction_id, o.record_uid, o.start_utc, o.lat, "
                    "o.lon, o.radius_m, o.kind, o.source_kind FROM pol_place_observation o JOIN w ON o.start_utc BETWEEN "
                    "w.lo AND w.hi WHERE o.case_id = :c AND o.extraction_id = ANY(CAST(:e AS uuid[]))"),
                    {**self.c, **wp, "e": phones}):
                recs.append({"ref": f"phone_record:{uid}", "kind": "position" if kind == "presence" else "media_position",
                             "at": M.as_utc(at), "phone": str(ext), "owner": owner.get(str(ext)),
                             "place": {"lat": lat, "lon": lon, "radius_m": rad, "source": src}})
            for ext, uid, at, body in self.db.execute(text(
                    f"WITH w(lo, hi) AS (VALUES {rng}) SELECT DISTINCT r.extraction_id, r.record_uid, r.first_instant, t.value "
                    "FROM pv_record r JOIN pv_text t ON t.record_uid = r.record_uid AND t.field_path = 'Body' JOIN w ON "
                    "r.first_instant BETWEEN w.lo AND w.hi + interval '3 days' WHERE r.case_id = :c AND "
                    "r.model_type = 'Notification' AND r.extraction_id = ANY(CAST(:e AS uuid[])) AND t.value ~ '\\$'"),
                    {**self.c, **wp, "e": phones}):
                alert = _read_alert(body, owner.get(str(ext)), everyone)
                if alert:
                    at = M.as_utc(at)
                    recs.append({"ref": f"phone_record:{uid}", "kind": "payment_alert", "at": at, "phone": str(ext),
                                 "body": body, **alert,
                                 "dup_key": ("pay", alert["owner"], tuple(alert["parties"]), abs(alert["amount_minor"]),
                                             at.astimezone(M.tz(self.zone())).date())})
        return recs

    def activity(self, people: list[dict], windows) -> dict[str, list[datetime]]:
        """Every record instant of each person's phones in the windows widened by a day: any kind at all, so a quiet
        phone is told from a phone with no messages."""
        out: dict[str, list[datetime]] = {}
        if not windows:
            return out
        rng = ", ".join(f"(CAST(:lo{i} AS timestamptz) - interval '24 hours', CAST(:hi{i} AS timestamptz) + interval '24 hours')"
                        for i in range(len(windows)))
        wp = {f"lo{i}": lo for i, (lo, _) in enumerate(windows)} | {f"hi{i}": hi for i, (_, hi) in enumerate(windows)}
        for p in people:
            if not p["phones"]:
                continue
            out[p["key"]] = sorted(M.as_utc(t) for (t,) in self.db.execute(text(
                f"WITH w(lo, hi) AS (VALUES {rng}) SELECT DISTINCT a.instant_utc FROM pol_activity_event a JOIN w ON "
                "a.instant_utc BETWEEN w.lo AND w.hi WHERE a.case_id = :c AND a.extraction_id = ANY(CAST(:e AS uuid[]))"),
                {**self.c, **wp, "e": p["phones"]}))
        return out

    # -- coverage ------------------------------------------------------------------------------------------------
    def phone_spans(self, extraction_id: str) -> tuple[list, int]:
        """The stretches of days a phone holds records on (``M.phone_spans``). The days are read one index probe per
        day (0.3 s for 1,030 days of a 540,000-record phone), not by counting every record."""
        if extraction_id not in self._phone_days:
            days = [r[0] for r in self.q(
                "WITH RECURSIVE d(at) AS ("
                " SELECT (SELECT min(instant_utc) FROM pol_activity_event WHERE extraction_id = :e)"
                " UNION ALL SELECT (SELECT min(instant_utc) FROM pol_activity_event WHERE extraction_id = :e AND "
                " instant_utc >= date_trunc('day', d.at, 'UTC') + interval '1 day') FROM d WHERE d.at IS NOT NULL)"
                " SELECT (at AT TIME ZONE 'UTC')::date FROM d WHERE at IS NOT NULL", e=extraction_id)]
            self._phone_days[extraction_id] = M.phone_spans(days)
            if self._phone_days[extraction_id][1]:
                self.set_aside[extraction_id] = self._phone_days[extraction_id][1]
        return self._phone_days[extraction_id]

    def coverage(self, people: list[dict], doc_ids: list[str]) -> dict:
        """What each source covers: a person's phones (the stretches of days they hold records on), the months their accounts hold ledger
        rows, phones that carry payment alerts, and each document's first to last dated row."""
        cov: dict[str, dict] = {}
        for p in people:
            c = cov.setdefault(p["key"], {"phone": [], "ledger": [], "alerts": []})
            for e in p["phones"]:
                spans, _ = self.phone_spans(e)
                if spans:
                    c["phone"] += spans
                    n = self.q("SELECT count(*) FROM pv_record r JOIN pv_text t ON t.record_uid = r.record_uid AND "
                               "t.field_path = 'Body' WHERE r.case_id = :c AND r.extraction_id = :e AND "
                               "r.model_type = 'Notification' AND t.value ~ '\\$'", e=e).scalar() or 0
                    if n:
                        c["alerts"] += spans
            for a in p["accounts"]:
                for (month,) in self.q(
                        "SELECT DISTINCT date_trunc('month', COALESCE(transaction_date, posted_date)) FROM "
                        "financial_transactions WHERE case_id = :c AND account_id = :a AND superseded_by_id IS NULL",
                        a=a):
                    if month:
                        start = M.as_utc(month).replace(hour=0)
                        nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
                        c["ledger"].append((start, nxt - timedelta(seconds=1)))
        for fid in doc_ids:
            rows = self.document_rows(fid)
            if rows:
                cov[f"doc:{fid}"] = {"doc": [(min(r["at"] for r in rows).replace(hour=0, minute=0),
                                              max(r["at"] for r in rows) + timedelta(hours=24))]}
        return cov

    def ledger_months(self, people: list[dict]) -> dict[str, list[str]]:
        out = {}
        for p in people:
            for a in p["accounts"]:
                out[a] = [m.strftime("%Y-%m") for (m,) in self.q(
                    "SELECT DISTINCT date_trunc('month', COALESCE(transaction_date, posted_date)) d FROM "
                    "financial_transactions WHERE case_id = :c AND account_id = :a ORDER BY d", a=a) if m]
        return out

    def account_labels(self, ids: list[str]) -> dict[str, str]:
        return {str(i): f"{n} {x}" for i, n, x in self.q(
            "SELECT id, institution_name, identifier_as_printed FROM financial_accounts WHERE case_id = :c AND "
            "id = ANY(CAST(:i AS uuid[]))", i=ids)} if ids else {}

    def statement_files_outside_ledger(self) -> list[str]:
        """Statement files in the case whose payments are not in the ledger, each said once: a second copy of a file
        the ledger already reads, or a statement still waiting for a person (a missing page). None of their payments
        is counted."""
        rows = self.q(
            "SELECT f.original_filename, bool_or(d.id IS NOT NULL) AS in_ledger, count(*) AS copies FROM evidence_files f "
            "LEFT JOIN financial_source_documents d ON d.case_id = f.case_id AND d.evidence_file_id = f.id "
            "WHERE f.case_id = :c AND f.deleted_at IS NULL AND f.original_filename ~* '\\.pdf$' AND "
            "f.original_filename ~* '(statement|exhibit|\\d{4}-\\d{2})' GROUP BY 1 ORDER BY 1").fetchall()
        ledger_names = {n for n, inside, _ in rows if inside}
        out = []
        for name, inside, copies in rows:
            if inside and copies > 1:
                out.append(f"{name} ({copies - 1} more cop{'y' if copies == 2 else 'ies'}, counted once)")
            elif not inside and any(_same_period(name, n) for n in ledger_names):
                out.append(f"{name} (not in the ledger; the same period is read from "
                           f"{next(n for n in sorted(ledger_names) if _same_period(name, n))})")
            elif not inside and _is_statement_like(name, ledger_names):
                out.append(f"{name} (not in the ledger yet)")
        return out

    def period(self, people: list[dict]) -> tuple[date, date] | None:
        """The days the comparison is drawn from: where the people's phones all hold records (their overlap), else
        every day any of their phones or accounts covers."""
        per_person = {p["key"]: [sp for e in p["phones"] for sp in self.phone_spans(e)[0]] for p in people}
        phone_spans = [(min(s[0] for s in v), max(s[1] for s in v)) for v in per_person.values() if v]
        if len(phone_spans) >= 2:
            lo, hi = max(s[0] for s in phone_spans), min(s[1] for s in phone_spans)
            if lo < hi:
                return lo.date(), hi.date()
        # no overlap of two phones: every day any of their phones or accounts covers (the full coverage, with ledgers)
        cov = self.coverage(people, [])
        spans = [s for c in cov.values() for k in ("phone", "ledger") for s in c.get(k, [])]
        if not spans:
            return None
        return min(s[0] for s in spans).date(), max(s[1] for s in spans).date()

    def phone_starts(self, people: list[dict]) -> dict[str, datetime]:
        """Each person's first outgoing phone record inside the phone's covered days (a 1970 or year-1 clock error is
        not a start): a number's use before it belongs to someone else's time with it."""
        out = {}
        for p in people:
            for e in p["phones"]:
                spans, _ = self.phone_spans(e)
                if not spans:
                    continue
                lo = self.q("SELECT min(sort_instant) FROM phone_comm_events WHERE case_id = :c AND extraction_id = :e "
                            "AND direction = 'outgoing' AND sort_instant >= :s", e=e, s=spans[0][0]).scalar()
                if lo and (p["key"] not in out or M.as_utc(lo) < out[p["key"]]):
                    out[p["key"]] = M.as_utc(lo)
        return out

    # -- counts for the weighing ---------------------------------------------------------------------------------
    def phrase_counts(self, phrases: list[str]) -> dict[str, int]:
        out = {}
        for ph in phrases[:200]:
            out[ph] = self.q("SELECT count(*) FROM phone_comm_events WHERE case_id = :c AND body ILIKE :p",
                             p=f"%{ph}%").scalar() or 0
        return out

    def place_stats(self, lat: float, lon: float, radius_m: float, exclude: list[str] | None = None) -> dict:
        r = max(radius_m, 100.0)
        dlat = r / 111_000.0
        from math import cos, radians
        dlon = r / (111_000.0 * max(0.2, abs(cos(radians(lat)))))
        rows = self.q("SELECT extraction_id, start_utc::date, lat, lon FROM pol_place_observation WHERE case_id = :c AND "
                      "kind = 'presence' AND lat BETWEEN :a AND :b AND lon BETWEEN :x AND :y",
                      a=lat - dlat, b=lat + dlat, x=lon - dlon, y=lon + dlon).fetchall()
        near: dict[str, set] = defaultdict(set)
        for e, d, la, lo in rows:
            if str(e) in set(exclude or ()):
                continue
            if M.haversine_m(lat, lon, la, lo) <= r:
                near[str(e)].add(d)
        total = self.q("SELECT count(DISTINCT extraction_id) FROM pol_place_observation WHERE case_id = :c").scalar() or 0
        return {"phones_near": len(near), "phones_total": max(total - len(set(exclude or ())), 0),
                "days": len({d for v in near.values() for d in v}), "radius_m": r}

    def contact_ever(self, a: dict, b: dict) -> int:
        """Messages, calls and e-mails anywhere in the case with both people on them (on either's phone)."""
        n = 0
        for x, y in ((a, b), (b, a)):
            if not x["phones"]:
                continue
            vals = [v for v in list(y["numbers"]) + list(y["handles"]) + list(y["emails"]) if v]
            if not vals:
                continue
            n += self.q("SELECT count(DISTINCT p.record_uid) FROM phone_participations p JOIN phone_comm_events c ON "
                        "c.record_uid = p.record_uid AND c.case_id = p.case_id WHERE p.case_id = :c AND "
                        "c.extraction_id = ANY(CAST(:e AS uuid[])) AND NOT COALESCE(p.is_phone_owner, false) AND "
                        "(regexp_replace(split_part(p.identifier_raw, '@', 1), '\\D', '', 'g') = ANY(:n) OR "
                        "lower(p.identifier_raw) = ANY(:v))",
                        e=x["phones"], n=[v for v in vals if v.isdigit()], v=[v for v in vals if not v.isdigit()]
                        ).scalar() or 0
        return n

    def identities_named(self, values: list[str]) -> list[dict]:
        """Every name each phone saved for these numbers, with the first and last record that carries the number."""
        out = []
        for v in values:
            for name, ext, first, last in self.q(
                    "SELECT n.name, n.extraction_id, i.first_instant, i.last_instant FROM phone_identity_names n JOIN "
                    "phone_identities i ON i.id = n.identity_id WHERE n.case_id = :c AND i.kind = 'phone' AND "
                    "regexp_replace(i.value_normalised, '\\D', '', 'g') = :v", v=v):
                out.append({"value": v, "name": name, "phone": str(ext), "first": M.as_utc(first), "last": M.as_utc(last)})
        return out

    def lookalike_names(self, person: dict) -> list[dict]:
        """Names saved on the phones, or printed in the ledger, that share a first name or a surname with the person
        but belong to a number or account that is not theirs: another person of the same name."""
        out = []
        for full in person["names"]:
            words = M.name_words(full)
            if len(words) < 2:
                continue
            rx = r"\m(" + re.escape(words[0]) + "|" + re.escape(words[-1]) + r")\M"
            for name, value, ext in self.q(
                    "SELECT DISTINCT n.name, i.value_normalised, n.extraction_id FROM phone_identity_names n JOIN "
                    "phone_identities i ON i.id = n.identity_id WHERE n.case_id = :c AND n.name ~* :rx", rx=rx):
                v = (value or "").lower()
                handle = "@" + v.split("@", 1)[1] if "@" in v and not v.startswith("@") and ":" in v.split("@")[0] else v
                num = M.norm_number(v) if "@" not in v else None
                if (num and num in person["numbers"]) or handle in person["handles"] or v in person["emails"] or \
                        any(M.names_match(n, name) for n in person["names"] if n):
                    continue
                out.append({"name": name, "value": ("+" + num) if num else value, "phone": str(ext),
                            "where": "saved on a phone"})
            for words_, tid in self.q(
                    "SELECT COALESCE(counterparty_raw, '') || ' ' || COALESCE(description, ''), id FROM "
                    "financial_transactions WHERE case_id = :c AND superseded_by_id IS NULL AND "
                    "(COALESCE(counterparty_raw, '') || ' ' || COALESCE(description, '')) ~* :rx LIMIT 50", rx=rx):
                if any(M.names_match(n, words_) for n in person["names"] if n) or \
                        self.q("SELECT account_id FROM financial_transactions WHERE id = :i", i=tid).scalar() and \
                        str(self.q("SELECT account_id FROM financial_transactions WHERE id = :i", i=tid).scalar()) in person["accounts"]:
                    continue
                out.append({"name": words_.strip(), "value": None, "ref": f"financial_transaction:{tid}",
                                "where": "in the ledger"})
        return out

    def number_history(self, value: str, before: datetime) -> list[dict]:
        """Records carrying the number earlier than ``before`` (a number in use by someone else first)."""
        rows = self.q(
            "SELECT DISTINCT c.record_uid, c.sort_instant, c.extraction_id FROM phone_participations p JOIN phone_comm_events c "
            "ON c.record_uid = p.record_uid AND c.case_id = p.case_id WHERE p.case_id = :c AND "
            "regexp_replace(split_part(p.identifier_raw, '@', 1), '\\D', '', 'g') = :v AND c.sort_instant < :b "
            "ORDER BY c.sort_instant LIMIT 50", v=value, b=before).fetchall()
        return [{"ref": f"phone_record:{u}", "at": M.as_utc(t), "phone": str(e)} for u, t, e in rows]

    def offsets(self, phones: list[str], windows) -> Counter:
        """How the instants of the people's records were read: an offset written in the record, or none."""
        out: Counter = Counter()
        if not phones or not windows:
            return out
        lo, hi = min(w[0] for w in windows), max(w[1] for w in windows)
        for status, n in self.q("SELECT offset_status, count(*) FROM pol_activity_event WHERE case_id = :c AND "
                                "extraction_id = ANY(CAST(:e AS uuid[])) AND instant_utc BETWEEN :lo AND :hi GROUP BY 1",
                                e=phones, lo=lo, hi=hi):
            out[status] += n
        return out

    def merchant_payments(self, people: list[dict], day: date) -> list[dict]:
        accs = [a for p in people for a in p["accounts"]]
        if not accs:
            return []
        return [{"ref": f"financial_transaction:{i}", "words": w, "amount_minor": a} for i, w, a in self.q(
            "SELECT id, COALESCE(counterparty_raw, '') || ' ' || COALESCE(description, ''), amount_minor FROM "
            "financial_transactions WHERE case_id = :c AND account_id = ANY(CAST(:a AS uuid[])) AND direction = 'debit' "
            "AND COALESCE(transaction_date, posted_date) = :d", a=accs, d=day)]

    # -- places a claim can name ---------------------------------------------------------------------------------
    def known_places(self) -> list[dict]:
        """Places a sentence can name: places a person has labelled (with a position) and the addresses on dossiers
        (named, with no position unless the dossier gives one). ``match`` is the words looked for in a sentence."""
        if getattr(self, "_known", None) is not None:
            return self._known
        out = []
        try:
            for label, lat, lon, rad in self.q("SELECT label, lat, lon, radius_m FROM pol_place_cluster WHERE case_id = :c "
                                               "AND label IS NOT NULL"):
                out.append({"name": label, "match": label, "lat": lat, "lon": lon, "radius_m": max(float(rad or 0), 100.0),
                            "how": "a place a person named on the map", "label": ""})
        except Exception:  # noqa: BLE001
            self.db.rollback()
        for p in self.people():
            for ct in (self.dossier_contacts().get(p["key"]) or []):
                if ct.get("kind") != "address" or not ct.get("value"):
                    continue
                val = str(ct["value"])
                head = re.split(r",|\d", val, maxsplit=1)[0].strip() or val
                pos = ct.get("position") if isinstance(ct.get("position"), dict) else {}
                if pos.get("value") != val:
                    pos = {}
                lat, lon = ct.get("lat"), ct.get("lon")
                how = "the address on the dossier"
                if lat is None and pos.get("lat") is not None:
                    # the address service's position for the dossier address (services.dossier_addresses)
                    lat, lon = pos["lat"], pos["lon"]
                    how = "the address on the dossier, placed by the address service (Read by Loupe, not confirmed)"
                out.append({"name": f"{head} ({ct.get('label') or 'address'} of {p['label']})", "match": head,
                            "label": str(ct.get("label") or ""), "owner": p["key"], "address": val,
                            "lat": lat, "lon": lon, "radius_m": 100.0, "how": how})
        self._known = out
        return out

    def dossier_contacts(self) -> dict:
        if getattr(self, "_contacts", None) is None:
            self._contacts = {f"person:{pid}": c for pid, c in self.q(
                "SELECT id, contacts FROM case_profiles WHERE case_id = :c AND archived_at IS NULL AND status = 'active'")}
        return self._contacts

    def routine_place(self, person: str, kind: str) -> dict | None:
        """Where a person's phone sits at night (home) or on weekday middays (work), read from its positions: the
        busiest ~200 m cell with at least ``HOME_MIN_POSITIONS`` positions. A reading by Loupe, said so in ``how``."""
        p = next((x for x in self.people() if x["key"] == person), None)
        if not p or not p["phones"]:
            return None
        zone = self.zone()
        hours = "BETWEEN 0 AND 5" if kind == "home" else "BETWEEN 10 AND 15 AND EXTRACT(isodow FROM o.start_utc AT TIME ZONE :z) < 6"
        rows = self.q("SELECT o.lat, o.lon FROM pol_place_observation o WHERE o.case_id = :c AND o.kind = 'presence' AND "
                      "o.extraction_id = ANY(CAST(:e AS uuid[])) AND EXTRACT(hour FROM o.start_utc AT TIME ZONE :z) " + hours,
                      e=p["phones"], z=zone).fetchall()
        cells = defaultdict(list)
        for la, lo in rows:
            cells[(round(la / 0.002), round(lo / 0.002))].append((la, lo))
        if not cells:
            return None
        best = max(cells.values(), key=len)
        if len(best) < 5:
            return None
        lat = sum(x[0] for x in best) / len(best)
        lon = sum(x[1] for x in best) / len(best)
        rad = max(150.0, max(M.haversine_m(lat, lon, la, lo) for la, lo in best))
        when = "between midnight and 5 am" if kind == "home" else "on weekdays between 10 am and 3 pm"
        return {"lat": lat, "lon": lon, "radius_m": round(rad, 1), "positions": len(best),
                "how": f"read from {p['label']}'s phone: {len(best)} positions {when} sit within about {int(rad)} m of one spot"}

    def facts(self) -> list[dict]:
        from services.corroborate import facts
        return facts.list_facts(self.db, self.case)


def text_key(words: str) -> str:
    """A fixed-size stand-in for a text, equal exactly when the texts are equal (128-bit digest). A record's key held
    a second copy of its whole body: on Phone reference 1 that was half of a 6 GB read (18 Nov)."""
    return hashlib.blake2b(words.encode("utf-8", "surrogatepass"), digest_size=16).hexdigest()


def contact_dup_key(kind, at, body, ends) -> tuple | None:
    """What makes two phone records one contact held on two phones: a message with the same text in the same minute
    between the same people; a call or a message with no text in the same minute between the same two known people
    (a call has no text, so without this a call held on both phones counted twice). Records with only one known end
    are never folded: two calls in one minute to two unknown numbers are two calls."""
    if at is None:
        return None
    who = frozenset(e for e in ends if e)
    minute = at.replace(second=0, microsecond=0)
    if body:
        return ("msg", minute, text_key(body.strip().casefold()), frozenset(ends))
    if len(who) >= 2:
        return ("bare", kind, minute, who)
    return None


def _period_key(name: str):
    m = re.search(r"(\d{4})-(\d{2})", name or "")
    month = None
    if not m:
        months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
                  "november", "december"]
        low = (name or "").lower()
        y = re.search(r"(19|20)\d{2}", low)
        mm = next((i + 1 for i, x in enumerate(months) if x in low), None)
        if y and mm:
            month = (y.group(0), f"{mm:02d}")
    else:
        month = (m.group(1), m.group(2))
    words = set(re.findall(r"[a-z]{3,}", (name or "").lower())) - {"pdf", "states", "exhibit", "statement",
                                                                  "january", "february", "march", "april", "may", "june",
                                                                  "july", "august", "september", "october", "november",
                                                                  "december"}
    return month, words


def _same_period(a: str, b: str) -> bool:
    ma, wa = _period_key(a)
    mb, wb = _period_key(b)
    return a != b and ma is not None and ma == mb and bool(wa & wb)


def _is_statement_like(name: str, ledger_names: set) -> bool:
    _, w = _period_key(name)
    return any(w & _period_key(n)[1] for n in ledger_names)


def _document_chunks(content: str) -> list[str]:
    """A table read into JSON (one object per row) gives one chunk per row; other text gives one chunk per line."""
    import json
    stripped = content.strip()
    if stripped.startswith("["):
        try:
            rows = json.loads(stripped)
        except ValueError:
            rows = None
        if isinstance(rows, list):
            def flat(v):
                if isinstance(v, dict):
                    return " ".join(flat(x) for x in v.values())
                if isinstance(v, list):
                    return " ".join(flat(x) for x in v)
                return "" if v is None else str(v)
            return [flat(r) for r in rows]
    return content.split("\n")


def _norm_value(v: str) -> str:
    v = (v or "").strip().lower()
    if v.startswith("@") or ("@" in v and not v.endswith("whatsapp.net")):
        return v
    return M.norm_number(v.split("@")[0]) or v


def _read_alert(body: str, phone_owner: str | None, everyone: list[dict]) -> dict | None:
    """A payment alert on a phone: who paid whom and how much, from the alert's own words. A name given as a first
    name and an initial ("Jane D.") is read only when one person of the case fits it, and is marked as such."""
    m = _AMOUNT.search(body or "")
    if not m or not phone_owner:
        return None
    amount = int(round(float(m.group(1).replace(",", "")) * 100))
    low = (body or "").casefold()

    def who(fragment: str):
        k = M.person_for_name(everyone, fragment)
        if k:
            return k, False
        # an initial is one letter, which ``M.name_words`` leaves out: read the words with initials kept
        w = re.sub(r"[^\w\s]", " ", fragment.casefold()).split()
        if len(w) >= 2 and len(w[-1]) == 1:
            fits = [p["key"] for p in everyone for n in p["names"] if n and M.name_words(n)[:1] == w[:1] and
                    M.name_words(n)[-1].startswith(w[-1])]
            if len(set(fits)) == 1:
                return fits[0], True
        return None, False
    if " sent " in low and " to " in low:
        k, partial = who(body.rsplit(" to ", 1)[1])
        return {"owner": phone_owner, "parties": [k] if k else [], "amount_minor": amount, "partial_name": partial}
    if "received" in low and " from " in low:
        k, partial = who(body.rsplit(" from ", 1)[1])
        return {"owner": k, "parties": [phone_owner], "amount_minor": amount, "partial_name": partial}
    # "posted to checking" names the account, not a check: only the word "check" (or "cheque") makes it one
    if "deposit" in low and re.search(r"\bcheck\b|\bcheque\b", low):
        # a check paid in on this phone's account; the payer is not in the alert's words
        return {"owner": None, "parties": [phone_owner], "amount_minor": amount, "check_deposit": True}
    if "deposit" in low:
        return {"owner": phone_owner, "parties": [], "amount_minor": amount, "cash_deposit": True}
    return None
