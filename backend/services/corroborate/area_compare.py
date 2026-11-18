"""Drawn Map areas compared over a time window (lx-overlapviews-b A; design Area.dc.html, screen 3).

Several areas at once, read over the same hours of one weekday (Friday 22:00 to Saturday 12:00, in the case's zone)
on every such night of the period. The nights asked about are the ones a person chooses (a theft night, a theory
date) or, when none are chosen, the nights on which anything is inside an area; every other night of the same
weekday is the "compared with" baseline, and its counts are always shown beside the nights asked about.

What counts as being in an area is the Corroborate store's presence reading (``pol_place_observation``): only a
position (``kind = 'presence'``) places a phone. A photo's place (EXIF, or the phone's photo-place records: Source
"Photos" / Category "Media Locations") is listed as "photo place, not a position" and never counts as presence, even
where the stored reading calls it presence (642 such points on the server; followups owns that fix). A searched or
harvested place is not a position either. Each point is tested on its own position with the Map's ray test.

Access rows (a badge log) have no position of their own. A document's dated rows count inside an area when a person
ticks the document for the area; Loupe suggests documents whose file name or text shares a distinctive word with the
area's name, and says the suggestion is by the name. Nothing is truncated: every night and every phone is returned.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from services.corroborate import model as M
from services.corroborate.area import _ring, inside_any

MAX_AREAS = 6
VISIT_GAP = timedelta(minutes=60)       # positions of one phone further apart than this inside an area are two visits
SAME_TIME = 45                          # visits on different nights within this many minutes of day are "the same time"
PHOTO_SOURCES = {"photos", "google photos", "apple photos", "location google photos", "location photos"}
_GENERIC = {"area", "warehouse", "unit", "street", "road", "north", "south", "east", "west", "second", "stop", "dock",
            "the", "and", "near", "place", "building", "office", "house", "home", "store", "storage", "park"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _hm(raw: str) -> time:
    h, m = (int(x) for x in raw.split(":"))
    return time(h, m)


def night_window(day: date, start: time, end: time, zone) -> tuple[datetime, datetime]:
    """The window of one night: ``day`` at ``start`` to ``end`` (the next day when ``end`` is not after ``start``)."""
    s = datetime.combine(day, start, zone)
    e = datetime.combine(day if end > start else day + timedelta(days=1), end, zone)
    return s.astimezone(timezone.utc), e.astimezone(timezone.utc)


def name_words(label: str) -> list[str]:
    """The distinctive words of an area's name: five letters or more, not a generic place word."""
    return [w for w in (x.casefold() for x in re.findall(r"[A-Za-z]{5,}", label or "")) if w not in _GENERIC]


def visits(times: list[datetime]) -> list[tuple[datetime, datetime]]:
    out: list[list[datetime]] = []
    for t in sorted(times):
        if out and t - out[-1][-1] <= VISIT_GAP:
            out[-1].append(t)
        else:
            out.append([t])
    return [(v[0], v[-1]) for v in out]


def _minute_of_night(at: datetime, zone, start: time) -> int:
    """Minutes after the window's start (so 23:30 and 01:30 order as they happen in one night)."""
    local = at.astimezone(zone)
    return ((local.hour * 60 + local.minute) - (start.hour * 60 + start.minute)) % 1440


def recurring_times(per_night: dict[str, list[tuple[datetime, datetime]]], zone, start: time) -> list[dict]:
    """Visit times that recur across nights: each visit's arrival as minutes into the night, grouped when within
    SAME_TIME of the group's first; a group gives its median arrival, its nights and its median stay."""
    items = sorted((_minute_of_night(a, zone, start), night, (b - a)) for night, vs in per_night.items() for a, b in vs)
    groups: list[list[tuple[int, str, timedelta]]] = []
    for it in items:
        if groups and it[0] - groups[-1][0][0] <= SAME_TIME:
            groups[-1].append(it)
        else:
            groups.append([it])
    out = []
    for g in groups:
        mins = int(statistics.median(x[0] for x in g))
        clock = (start.hour * 60 + start.minute + mins) % 1440
        out.append({"time": f"{clock // 60:02d}:{clock % 60:02d}", "nights": sorted({x[1] for x in g}),
                    "stay_min": int(statistics.median(x[2].total_seconds() / 60 for x in g))})
    return out


class AreaReader:
    """The case's points and access rows for areas, read once for the whole period."""

    def __init__(self, store):
        self.store = store

    def phone_names(self) -> dict[str, str]:
        out = {}
        for p in self.store.people():
            for e in p["phones"]:
                out[e] = p["label"]
        return out

    def phone_labels(self) -> dict[str, str]:
        from services.phone.readings import phone_labels
        return phone_labels(self.store.db.connection(), self.store.case)

    def period(self) -> tuple[date, date] | None:
        spans = []
        for (e,) in self.store.q("SELECT id FROM phone_extractions WHERE case_id = :c AND standing = 'active'"):
            spans += self.store.phone_spans(str(e))[0]
        if not spans:
            return None
        return min(s[0] for s in spans).date(), max(s[1] for s in spans).date()

    def points(self, bbox, lo: datetime, hi: datetime) -> list[dict]:
        w, s, e, n = bbox
        rows = self.store.q(
            "SELECT o.record_uid, o.extraction_id, o.start_utc, o.lat, o.lon, o.radius_m, o.kind, o.source_kind, "
            "(SELECT string_agg(lower(t.value), '|') FROM pv_text t WHERE t.record_uid = o.record_uid AND "
            " t.field_path IN ('Source', 'Category')) AS src FROM pol_place_observation o WHERE o.case_id = :c AND "
            "o.lat BETWEEN :s AND :n AND o.lon BETWEEN :w AND :e AND o.start_utc BETWEEN :lo AND :hi",
            s=s, n=n, w=w, e=e, lo=lo, hi=hi).fetchall()
        out = []
        for uid, ext, at, lat, lon, rad, kind, src_kind, src in rows:
            words = set((src or "").split("|"))
            photo = src_kind == "media_exif" or kind == "media" or bool(words & PHOTO_SOURCES) or "media locations" in words
            what = "photo_place" if photo else ("position" if kind == "presence" else "not_position")
            out.append({"ref": f"phone_record:{uid}", "phone": str(ext), "at": M.as_utc(at), "lat": float(lat),
                        "lon": float(lon), "radius_m": rad, "what": what, "source_kind": src_kind})
        return out

    def documents_with_rows(self) -> list[dict]:
        """Documents whose text holds dated and timed rows (an access log), with their name and first words."""
        out = []
        for fid, name, content in self.store.q(
                "SELECT f.id, f.original_filename, t.content FROM evidence_document_texts t JOIN evidence_files f ON "
                "f.id = t.evidence_file_id WHERE f.case_id = :c AND f.deleted_at IS NULL AND t.content ~ "
                "'\\d{4}-\\d{2}-\\d{2}[ T]\\d{2}:\\d{2}'"):
            out.append({"id": str(fid), "name": name, "text": (content or "")[:4000]})
        return out


def suggest_documents(label: str, docs: list[dict]) -> list[dict]:
    words = name_words(label)
    out = []
    for d in docs:
        hay = f"{d['name']} {d['text']}".casefold()
        hit = next((w for w in words if w in hay), None)
        if hit:
            out.append({"id": d["id"], "name": d["name"], "why": f"Suggested by Loupe: the document shares the word "
                                                                  f"“{hit}” with the area's name. Untick it if it is not about this place."})
    return out


def compare_areas(store, areas: list[dict], *, weekday: int, start: str, end: str, nights: list[str] | None = None,
                  period: tuple[date, date] | None = None, documents: dict[int, list[str]] | None = None,
                  reader: AreaReader | None = None) -> dict[str, Any]:
    """Each area over the window on every night of the weekday in the period: who is in each and in what order,
    everything inside by kind, the night-by-night strip, and the other nights as the baseline."""
    if not areas:
        raise ValueError("Draw at least one area.")
    if len(areas) > MAX_AREAS:
        raise ValueError(f"Compare at most {MAX_AREAS} areas at once; {len(areas)} are drawn.")
    if not 0 <= weekday <= 6:
        raise ValueError("Choose a day of the week.")
    reader = reader or AreaReader(store)
    zone_name = store.zone()
    zone = M.tz(zone_name)
    t0, t1 = _hm(start), _hm(end)
    rings = [_ring(a["ring"]) for a in areas]
    labels = [str(a.get("label") or f"Area {chr(65 + i)}") for i, a in enumerate(areas)]
    period = period or reader.period()
    if not period:
        return {"zone": zone_name, "areas": [], "nights": [], "words": "No phone in the case holds records to read."}
    lo, hi = period
    days = [lo + timedelta(days=n) for n in range((hi - lo).days + 1) if (lo + timedelta(days=n)).weekday() == weekday]
    windows = {d.isoformat(): night_window(d, t0, t1, zone) for d in days}
    xs = [x for r in rings for x, _ in r]
    ys = [y for r in rings for _, y in r]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    span_lo = datetime.combine(lo, time.min, timezone.utc) - timedelta(days=1)
    span_hi = datetime.combine(hi, time.max, timezone.utc) + timedelta(days=2)
    pts = reader.points(bbox, span_lo, span_hi)
    names = reader.phone_names()
    plabels = reader.phone_labels()

    def who(ext: str) -> str:
        return names.get(ext) or plabels.get(ext) or "a phone"

    def night_of(at: datetime) -> str | None:
        for d, (a, b) in windows.items():
            if a <= at <= b:
                return d
        return None

    docs_all = reader.documents_with_rows()
    documents = documents if documents is not None else {i: [d["id"] for d in suggest_documents(labels[i], docs_all)]
                                                         for i in range(len(areas))}
    people = store.people()
    by_person = {p["key"]: p["label"] for p in people}

    per_area = []
    for i, ring in enumerate(rings):
        inside = [p for p in pts if inside_any(p["lon"], p["lat"], [ring])]
        rows = []
        for fid in documents.get(i, []) or documents.get(str(i), []) or []:
            src = next((d["name"] for d in docs_all if d["id"] == fid), fid)
            for r in store.document_rows(fid):
                rows.append({**r, "ref": f"document_row:{fid}:{r['index']}", "source_label": src})
        per_area.append({"inside": inside, "rows": rows})

    # the nights asked about: chosen, else nights with anything inside an area (said so)
    busy = sorted(({night_of(p["at"]) for a in per_area for p in a["inside"] if p["what"] == "position"} |
                   {night_of(r["at"]) for a in per_area for r in a["rows"]}) - {None})
    chosen = [n for n in (nights or []) if n in windows]
    unknown = [n for n in (nights or []) if n not in windows]
    asked = chosen if nights else busy
    basis = ("the nights you chose" if nights else "the nights with a position or access row inside an area")
    other = [d for d in windows if d not in asked]

    out_areas = []
    strip: dict[str, dict] = {d: {"night": d, "label": datetime.fromisoformat(d).strftime("%a %d %b %Y"),
                                  "asked": d in asked, "areas": []} for d in windows}
    for i, a in enumerate(per_area):
        by_phone: dict[str, dict[str, list[datetime]]] = defaultdict(lambda: defaultdict(list))
        photo_by_phone: dict[str, set] = defaultdict(set)
        not_pos = 0
        outside: dict[str, list[datetime]] = defaultdict(list)
        counts = {"positions": 0, "position_phones": set(), "access_rows": 0, "doors": Counter(), "photo_places": 0,
                  "photo_phones": set(), "not_positions": 0}
        base = {"positions": 0, "access_rows": 0, "photo_places": 0, "nights_with_any": 0}
        base_nights = set()
        for p in a["inside"]:
            n = night_of(p["at"])
            if n is None:
                if p["what"] == "position":
                    outside[p["phone"]].append(p["at"])
                continue
            if n in asked:
                if p["what"] == "position":
                    by_phone[p["phone"]][n].append(p["at"])
                    counts["positions"] += 1
                    counts["position_phones"].add(p["phone"])
                elif p["what"] == "photo_place":
                    photo_by_phone[p["phone"]].add(n)
                    counts["photo_places"] += 1
                    counts["photo_phones"].add(p["phone"])
                else:
                    counts["not_positions"] += 1
                    not_pos += 1
            else:
                key = {"position": "positions", "photo_place": "photo_places"}.get(p["what"])
                if key:
                    base[key] += 1
                if p["what"] == "position":
                    base_nights.add(n)
            strip[n]["areas"].append({"area": i, "at": M.iso(p["at"]), "who": who(p["phone"]), "phone": p["phone"],
                                      "what": p["what"], "ref": p["ref"]})
        access_by_person: dict[str, dict[str, list[tuple[datetime, str]]]] = defaultdict(lambda: defaultdict(list))
        for r in a["rows"]:
            n = night_of(r["at"])
            if n is None:
                continue
            door = _door(r["text"])
            if n in asked:
                counts["access_rows"] += 1
                if door:
                    counts["doors"][door] += 1
                for k in r["parties"] or ["unnamed"]:
                    access_by_person[k][n].append((r["at"], door))
            else:
                base["access_rows"] += 1
                base_nights.add(n)
            strip[n]["areas"].append({"area": i, "at": M.iso(r["at"]), "who": ", ".join(by_person.get(k, k) for k in r["parties"]) or "unnamed",
                                      "what": "access_row", "door": door, "ref": r["ref"], "text": r["text"][:160]})
        base["nights_with_any"] = len(base_nights)
        phones_rows = []
        for ext, per_night in by_phone.items():
            vs = {n: visits(ts) for n, ts in per_night.items()}
            phones_rows.append({"phone": ext, "who": who(ext), "nights": sorted(per_night), "times": recurring_times(vs, zone, t0),
                                "first": {n: M.iso(min(ts)) for n, ts in per_night.items()}})
        outside_rows = []
        for ext, ts in outside.items():
            local = [t.astimezone(zone) for t in ts]
            hours = Counter(t.hour for t in local).most_common(1)[0][0]
            outside_rows.append({"phone": ext, "who": who(ext), "days": len({t.date() for t in local}), "positions": len(ts),
                                 "from": min(local).date().isoformat(), "to": max(local).date().isoformat(),
                                 "usual_hour": f"{hours:02d}:00 to {(hours + 1) % 24:02d}:00"})
        suggested = suggest_documents(labels[i], docs_all)
        chosen_docs = documents.get(i, []) or documents.get(str(i), []) or []
        out_areas.append({
            "index": i, "label": labels[i],
            "inside": {"positions": counts["positions"], "position_phones": len(counts["position_phones"]),
                       "access_rows": counts["access_rows"], "doors": dict(counts["doors"]),
                       "photo_places": counts["photo_places"], "photo_phones": len(counts["photo_phones"]),
                       "not_positions": counts["not_positions"]},
            "baseline": base,
            "phones": sorted(phones_rows, key=lambda r: (-len(r["nights"]), r["who"])),
            "photo_only": [{"phone": e, "who": who(e), "nights": sorted(ns)} for e, ns in photo_by_phone.items()
                           if e not in by_phone],
            "access": [{"person": k, "who": by_person.get(k, "unnamed row"),
                        "nights": sorted(v), "times": _access_times(v, zone)} for k, v in access_by_person.items()],
            "outside_window": sorted(outside_rows, key=lambda r: -r["days"]),
            "documents": [{"id": d, "name": next((x["name"] for x in docs_all if x["id"] == d), d),
                           "why": next((s["why"] for s in suggested if s["id"] == d), "Chosen by you.")} for d in chosen_docs],
            "suggested_documents": suggested,
        })

    order = _order(out_areas, asked)
    for d in strip.values():
        d["areas"].sort(key=lambda x: x["at"])
    wd = WEEKDAYS[weekday]
    end_day = WEEKDAYS[(weekday + (0 if t1 > t0 else 1)) % 7]
    window_words = f"{wd}s {start} to {end_day if end_day != wd else ''} {end}".replace("  ", " ")
    members = [{"type": "phone_record", "id": p["ref"].split(":", 1)[1], "label": f"Position in {labels[i]}"}
               for i, a in enumerate(per_area) for p in a["inside"]
               if p["what"] == "position" and night_of(p["at"]) in asked]
    members += [{"type": "document_row", "id": r["ref"].split(":", 1)[1], "label": r["text"][:120]}
                for a in per_area for r in a["rows"] if night_of(r["at"]) in asked]
    return {
        "zone": zone_name, "window": {"weekday": weekday, "start": start, "end": end, "words": window_words},
        "period": {"from": lo.isoformat(), "to": hi.isoformat()},
        "asked": {"nights": asked, "basis": basis, "unknown": unknown},
        "compared_with": {"nights": other, "words": f"the other {len(other)} {wd}s, {lo:%d %b} to {hi:%d %b %Y}"},
        "areas": out_areas, "order": order,
        "strip": [strip[d] for d in sorted(strip)],
        "members": members,
    }


_DOOR = re.compile(r"(Staff entrance|Dock \d+|Gate \w+|Door \w+|Main entrance|Side entrance)", re.I)


def _door(text: str) -> str | None:
    m = _DOOR.search(text or "")
    return m.group(1) if m else None


def _access_times(per_night: dict[str, list[tuple[datetime, str]]], zone) -> list[dict]:
    c: dict[tuple[str, str], set] = defaultdict(set)
    for n, items in per_night.items():
        for at, door in items:
            c[(at.astimezone(zone).strftime("%H:%M"), door or "")].add(n)
    return [{"time": t, "door": d or None, "nights": len(ns)} for (t, d), ns in sorted(c.items())]


def _order(areas: list[dict], asked: list[str]) -> list[dict]:
    """For each phone seen in two areas on a night asked about: which area it reached first, on how many nights."""
    if len(areas) < 2:
        return []
    out = []
    first: dict[str, dict[int, dict[str, str]]] = defaultdict(dict)
    whos = {}
    for a in areas:
        for r in a["phones"]:
            first[r["phone"]][a["index"]] = r["first"]
            whos[r["phone"]] = r["who"]
    for ext, per_area in first.items():
        if len(per_area) < 2:
            continue
        seq = Counter()
        for n in asked:
            seen = sorted((at[n], i) for i, at in per_area.items() if n in at)
            if len(seen) >= 2:
                seq[tuple(i for _, i in seen)] += 1
        for s, k in seq.most_common():
            out.append({"phone": ext, "who": whos[ext], "sequence": list(s), "nights": k, "of": len(asked)})
    return out
