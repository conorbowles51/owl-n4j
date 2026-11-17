"""Where the link rules read the case (lx-overlaps B). Read-only; every query is scoped to the case.

``Sources`` is what the engine asks for; ``DbSources`` answers from Postgres (the ledger, the phone activity and
position tables, evidence and the graph). Tests give the engine a fake with the same four methods. A method that
cannot answer says so (raises ``OutOfReach`` with the reason) and the engine reports it as out of reach, never as
"nothing found".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from services.relations import rules


class OutOfReach(RuntimeError):
    """A search that could not be run, with the reason a person can read."""


def _uid(value: Any):
    import uuid
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError):
        return None


def _mid(day) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


class DbSources:
    def __init__(self, db, case_id):
        self.db, self.case = db, str(case_id)

    # -- items -------------------------------------------------------------------------------------------------
    def load_items(self, members: list[dict]) -> list[dict]:
        """Each member as an item: ref, type, label, at, precision, place, identifiers, names, amount, phone."""
        from services import theory_additions
        facts = {f["ref"]: f for f in theory_additions.member_facts(self.db, self.case, members)}
        items = []
        for m in members:
            ref = f"{m['type']}:{m['id']}"
            fact = facts.get(ref, {})
            label = fact.get("label") or m.get("label") or ref
            item = {"ref": ref, "type": m["type"], "id": m["id"], "label": label, "at": None, "identifiers": [],
                    "names": [], "state": fact.get("state", "present"), "text": fact.get("text", "")}
            if m.get("quote"):
                item["text"] = str(m["quote"])
                item["label"] = f"{label}: “{str(m['quote'])[:60]}”"
            item["identifiers"] = rules.extract_identifiers(item["text"] + " " + str(label))
            getattr(self, "_" + m["type"], self._plain)(item, m, fact)
            items.append(item)
        return items

    def _plain(self, item, m, fact):
        day = fact.get("date")
        if day:
            item["at"] = f"{day}T00:00:00+00:00"
            item["precision"] = "day"
        item["names"] = [item["label"]]

    _graph_entity = _timeline_event = _entry = _plain

    def _financial_transaction(self, item, m, fact):
        row = self.db.execute(text(
            "SELECT counterparty_raw, description, ref_id, transaction_date, posted_date FROM financial_transactions "
            "WHERE case_id = :c AND id = :i"), {"c": self.case, "i": m["id"]}).first()
        item["time_kind"] = "financial_transaction"
        if fact.get("date"):
            item["at"] = f"{fact['date']}T00:00:00+00:00"
            item["precision"] = "day"
        item["amount_minor"], item["currency"] = fact.get("amount_minor"), fact.get("currency")
        try:  # a place a person attached to the payment (pol_manual_place); none is attached unless someone did
            from services.pattern_of_life import money as pol_money
            placed = pol_money.current_places(self.db.connection(), self.case, [m["id"]]).get(m["id"])
        except Exception:  # noqa: BLE001 - without it the payment simply has no place
            placed = None
        if placed:
            item["place"] = {"lat": placed["lat"], "lon": placed["lon"], "radius_m": float(placed["radius_m"] or 0),
                             "source": "attached by a person"}
        if row:
            item["names"] = [n for n in (row[0],) if n]
            item["identifiers"] += rules.extract_identifiers(" ".join(str(x) for x in (row[0], row[1], row[2]) if x))

    def _financial_account(self, item, m, fact):
        row = self.db.execute(text(
            "SELECT institution_name, identifier_normalised, identifier_as_printed FROM financial_accounts "
            "WHERE case_id = :c AND id = :i"), {"c": self.case, "i": m["id"]}).first()
        if row:
            item["names"] = [row[0]] if row[0] else []
            for v in (row[1], row[2]):
                num = rules.norm_number(v or "")
                if num:
                    item["identifiers"].append({"kind": "number", "value": num, "display": v})

    def _financial_party(self, item, m, fact):
        item["names"] = [item["label"]]

    def _evidence(self, item, m, fact):
        item["names"] = []

    def _place(self, item, m, fact):
        parts = str(m["id"]).split(",")
        try:
            lat, lon, radius = (float(x) for x in parts[:3])
        except ValueError:
            return
        if len(parts) == 4 and _uid(parts[3]):  # a phone's positions in one place, made one item (runs.pair_units)
            item["phone"] = parts[3]
            item["place"] = {"lat": lat, "lon": lon, "radius_m": radius, "source": "positions of one phone"}
            return
        if len(parts) != 3:
            return
        item["place"] = {"lat": lat, "lon": lon, "radius_m": radius, "source": "chosen on the map"}

    def _phone_record(self, item, m, fact):
        u = _uid(m["id"])
        if not u:
            return
        ev = self.db.execute(text(
            "SELECT extraction_id, kind, sort_instant, thread_key FROM phone_comm_events WHERE case_id = :c "
            "AND record_uid = :u ORDER BY sort_instant NULLS LAST LIMIT 1"), {"c": self.case, "u": u}).first()
        if ev:
            item["phone"], item["at"] = str(ev[0]), ev[2].isoformat() if ev[2] else None
            item["time_kind"] = "phone_call" if ev[1] == "call" else "phone_message"
        pt = self.db.execute(text(
            "SELECT extraction_id, lat, lon, accuracy_m, source_kind, instant FROM phone_location_points "
            "WHERE case_id = :c AND record_uid = :u AND lat IS NOT NULL ORDER BY instant NULLS LAST LIMIT 1"),
            {"c": self.case, "u": u}).first()
        if pt:
            item["phone"] = str(pt[0])
            item["at"] = item["at"] or (pt[5].isoformat() if pt[5] else None)
            item["place"] = {"lat": pt[1], "lon": pt[2], "radius_m": float(pt[3] or 0), "source": pt[4]}
            item.setdefault("time_kind", "phone_location")
        kind_word = {"phone_call": "Call", "phone_message": "Message", "phone_location": "Position"}.get(item.get("time_kind"), "Phone record")
        if item.get("at"):
            when = rules.parse_when(item["at"])
            item["label"] = f"{kind_word} {when:%Y-%m-%d %H:%M} on phone {item.get('phone', '')[:8]}".strip()
        if not ev and not pt:
            act = self.db.execute(text(
                "SELECT extraction_id, instant_utc FROM pol_activity_event WHERE case_id = :c AND record_uid = :u "
                "ORDER BY instant_utc LIMIT 1"), {"c": self.case, "u": u}).first()
            if act:
                item["phone"], item["at"] = str(act[0]), act[1].isoformat() if act[1] else None
                if act[1]:
                    item["label"] = f"Phone record {act[1]:%Y-%m-%d %H:%M} on phone {str(act[0])[:8]}"
        for row in self.db.execute(text(
                "SELECT identifier_raw, name_in_record FROM phone_participations WHERE case_id = :c AND record_uid = :u "
                "AND COALESCE(is_phone_owner, false) = false"), {"c": self.case, "u": u}):
            item["identifiers"] += rules.extract_identifiers(row[0] or "") + (
                [{"kind": "number", "value": rules.norm_number(row[0]), "display": row[0]}]
                if rules.norm_number(row[0] or "") else [])
            if row[1]:
                item["names"].append(row[1])

    # -- baseline ----------------------------------------------------------------------------------------------
    def base(self, items: list[dict]) -> dict:
        """Days in the period with a record of each kind, read from the case (never estimated)."""
        c = {"c": self.case}
        row = self.db.execute(text(
            "SELECT count(DISTINCT COALESCE(transaction_date, posted_date)), min(COALESCE(transaction_date, posted_date)), "
            "max(COALESCE(transaction_date, posted_date)) FROM financial_transactions WHERE case_id = :c "
            "AND superseded_by_id IS NULL"), c).first()
        days: dict[str, int] = {}
        starts, ends = [], []
        if row and row[0]:
            days["financial_transaction"] = row[0]
            starts.append(_mid(row[1])); ends.append(_mid(row[2]))
        for kind, label in (("call", "phone_call"), ("message", "phone_message")):
            r = self.db.execute(text(
                "SELECT count(DISTINCT sort_instant::date), min(sort_instant), max(sort_instant) FROM phone_comm_events "
                "WHERE case_id = :c AND kind = :k AND sort_instant IS NOT NULL"), {**c, "k": kind}).first()
            if r and r[0]:
                days[label] = r[0]; starts.append(r[1]); ends.append(r[2])
        r = self.db.execute(text(
            "SELECT count(DISTINCT instant::date), min(instant), max(instant) FROM phone_location_points "
            "WHERE case_id = :c AND instant IS NOT NULL"), c).first()
        if r and r[0]:
            days["phone_location"] = r[0]; starts.append(r[1]); ends.append(r[2])
        dated = [rules.parse_when(i.get("at")) for i in items if i.get("at")]
        lo = min(starts + dated) if (starts or dated) else None
        hi = max(ends + dated) if (ends or dated) else None
        period = ((hi.date() - lo.date()).days + 1) if lo and hi else 0
        for i in items:  # a kind with no count of its own is read as no baseline, not as zero
            pass
        return {"period_days": period, "days_with": days, "start": lo.isoformat() if lo else None,
                "end": hi.isoformat() if hi else None}

    def identifier_counts(self, kind: str, value: str) -> dict | None:
        c = {"c": self.case}
        total = self.db.execute(text("SELECT count(*) FROM financial_transactions WHERE case_id = :c"), c).scalar() or 0
        if not total:
            return None
        if kind == "name":
            n = self.db.execute(text(
                "SELECT count(*) FROM financial_transactions WHERE case_id = :c AND "
                "lower(COALESCE(counterparty_raw, '') || ' ' || COALESCE(description, '')) LIKE :v"),
                {**c, "v": f"%{value}%"}).scalar() or 0
        else:
            n = self.db.execute(text(
                "SELECT count(*) FROM financial_transactions WHERE case_id = :c AND "
                "regexp_replace(COALESCE(counterparty_raw, '') || COALESCE(description, ''), '[^0-9a-zA-Z@.]', '', 'g') "
                "ILIKE :v"), {**c, "v": f"%{value}%"}).scalar() or 0
        return {"count": n, "base": total, "unit": "ledger rows"}

    def place_stats(self, lat: float, lon: float, radius_m: float) -> dict:
        dlat = radius_m / 111_000.0
        dlon = radius_m / (111_000.0 * max(0.2, abs(__import__("math").cos(__import__("math").radians(lat)))))
        rows = self.db.execute(text(
            "SELECT extraction_id, instant::date AS d, lat, lon FROM phone_location_points WHERE case_id = :c AND "
            "instant IS NOT NULL AND lat BETWEEN :a AND :b AND lon BETWEEN :x AND :y"),
            {"c": self.case, "a": lat - dlat, "b": lat + dlat, "x": lon - dlon, "y": lon + dlon}).fetchall()
        near = {}
        for ext, d, la, lo in rows:
            if rules.haversine_m(lat, lon, la, lo) <= radius_m:
                near.setdefault(str(ext), set()).add(d)
        total = self.db.execute(text(
            "SELECT count(DISTINCT extraction_id) FROM phone_location_points WHERE case_id = :c"), {"c": self.case}).scalar() or 0
        active = {str(e): n for e, n in self.db.execute(text(
            "SELECT extraction_id, count(DISTINCT instant::date) FROM phone_location_points WHERE case_id = :c "
            "AND instant IS NOT NULL GROUP BY 1"), {"c": self.case})}
        return {"phones_near": len(near), "phones_total": total, "days_at_place": {k: len(v) for k, v in near.items()},
                "days_active": active}

    def pair_stats(self, ea: str, eb: str) -> dict:
        """Days the two phones were within about 30 minutes and 250 m of each other, and days both were active."""
        # an equi-join over each of the other phone's cells and its 26 neighbours (the half-hour and 450 m squares beside it)
        # reads the same thing as a range join, in milliseconds on 67,000 positions; the range join timed out at 90 s
        row = self.db.execute(text("""
            WITH a AS (SELECT floor(extract(epoch FROM instant) / 900) AS bin, round(lat / 0.002) AS la, round(lon / 0.002) AS lo,
                              instant::date AS d FROM phone_location_points
                       WHERE case_id = :c AND extraction_id = CAST(:a AS uuid) AND instant IS NOT NULL AND lat IS NOT NULL),
                 b AS (SELECT DISTINCT floor(extract(epoch FROM instant) / 900) AS bin, round(lat / 0.002) AS la, round(lon / 0.002) AS lo,
                              instant::date AS d FROM phone_location_points
                       WHERE case_id = :c AND extraction_id = CAST(:b AS uuid) AND instant IS NOT NULL AND lat IS NOT NULL),
                 bx AS (SELECT DISTINCT b.bin + k1 AS bin, b.la + k2 AS la, b.lo + k3 AS lo
                        FROM b CROSS JOIN generate_series(-1, 1) k1 CROSS JOIN generate_series(-1, 1) k2 CROSS JOIN generate_series(-1, 1) k3)
            SELECT (SELECT count(DISTINCT a.d) FROM a JOIN bx ON bx.bin = a.bin AND bx.la = a.la AND bx.lo = a.lo),
                   (SELECT count(*) FROM (SELECT d FROM a INTERSECT SELECT d FROM b) x)"""),
            {"c": self.case, "a": ea, "b": eb}).first()
        return {"days_together": int(row[0] or 0), "days_both_active": int(row[1] or 0)}

    # -- phone streams -----------------------------------------------------------------------------------------
    def relay(self, phones: list[str]) -> tuple[list[dict], int]:
        """Relay chains found in SQL: a phone's contact with a counterpart, then another phone's contact with the same
        counterpart within ten minutes. One chain per pair of phones, counterpart and day. Returns (pairs, events read)."""
        if len(phones) < 2:
            return [], 0
        read = self.db.execute(text(
            "SELECT count(*) FROM pol_activity_event WHERE case_id = :c AND extraction_id = ANY(CAST(:e AS uuid[])) "
            "AND instant_utc IS NOT NULL AND activity_class = 'interaction' AND counterpart_identity_id IS NOT NULL"),
            {"c": self.case, "e": phones}).scalar() or 0
        rows = self.db.execute(text("""
            SELECT DISTINCT ON (a.extraction_id, b.extraction_id, a.counterpart_identity_id, a.instant_utc::date)
                   a.extraction_id, b.extraction_id, a.counterpart_identity_id, a.instant_utc, b.instant_utc
            FROM pol_activity_event a JOIN pol_activity_event b
              ON b.case_id = a.case_id AND b.counterpart_identity_id = a.counterpart_identity_id
             AND b.extraction_id <> a.extraction_id AND b.instant_utc > a.instant_utc
             AND b.instant_utc <= a.instant_utc + interval '10 minutes'
            WHERE a.case_id = :c AND a.extraction_id = ANY(CAST(:e AS uuid[])) AND b.extraction_id = ANY(CAST(:e AS uuid[]))
              AND a.activity_class = 'interaction' AND b.activity_class = 'interaction'
              AND a.counterpart_identity_id IS NOT NULL
            ORDER BY a.extraction_id, b.extraction_id, a.counterpart_identity_id, a.instant_utc::date, (b.instant_utc - a.instant_utc)"""),
            {"c": self.case, "e": phones}).fetchall()
        return [{"first": str(r[0]), "second": str(r[1]), "via": str(r[2]), "first_at": r[3].isoformat(),
                 "second_at": r[4].isoformat()} for r in rows], int(read)

    def silences(self, phones: list[str], minimum_hours: int = 6) -> tuple[dict[str, list[tuple[datetime, datetime]]], int]:
        """Each phone's silences of at least ``minimum_hours`` between two interaction times, found in SQL."""
        gaps: dict[str, list] = {p: [] for p in phones}
        read = 0
        for ext in phones:
            read += self.db.execute(text(
                "SELECT count(DISTINCT instant_utc) FROM pol_activity_event WHERE case_id = :c AND extraction_id = CAST(:e AS uuid) "
                "AND instant_utc IS NOT NULL AND activity_class = 'interaction'"), {"c": self.case, "e": ext}).scalar() or 0
            for t, n in self.db.execute(text("""
                SELECT t, n FROM (SELECT instant_utc AS t, lead(instant_utc) OVER (ORDER BY instant_utc) AS n
                                  FROM (SELECT DISTINCT instant_utc FROM pol_activity_event
                                        WHERE case_id = :c AND extraction_id = CAST(:e AS uuid) AND instant_utc IS NOT NULL
                                          AND activity_class = 'interaction') x) y
                WHERE n - t >= make_interval(hours => :h) ORDER BY t"""), {"c": self.case, "e": ext, "h": minimum_hours}):
                gaps[ext].append((t, n))
        return gaps, int(read)

    def together_apart(self, ea: str, eb: str) -> dict:
        """The existing who-used-which-phone measure over the days both phones hold owner interaction."""
        from services.phone_analysis import device_users
        conn = self.db.connection()
        return device_users.complementary(device_users._interaction_bins(conn, ea), device_users._interaction_bins(conn, eb))
