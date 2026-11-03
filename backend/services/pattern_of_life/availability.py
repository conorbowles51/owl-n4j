"""Data availability bands and the hourly rollup (04 section 5, unit U4).

An empty period must read as "No data" or as "Phone recording, no use seen", never ambiguously (plan 11.2 item 4).

- Observed segments: per recording stream, consecutive instants no further apart than the stream family's
  ``MAX_GAP_S`` merge into one segment; an interval is covered throughout. Messages, calls, web, search, email,
  social, notifications and app use never establish observation (their rate follows the person; 04 decision 3 and
  decision 23), nor do logs (content-dependent).
- Switched off: from an off event to the next on event; an on event with no off in the 24 h before it gives an
  inferred off period from the end of the last observed segment before it (5.3 step 5).
- After the extraction: every instant after the report's ``DeviceInfoExtractionStartDateTime``; events stamped
  after it keep their place and gain the flag ``after_extraction_time`` (5.3 step 1).
- Hour states (5.3 step 6) are derived on read from the bands and the rollup: ``after_extraction``,
  ``powered_off``, ``powered_off_inferred``, ``interaction``, ``data_no_interaction``, ``no_data``.

``MAX_GAP_S`` replaces 5.3's provisional defaults with values measured by M4 on the 14 server reports (04 decision 23).
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from services.pattern_of_life import activity

# 04 decision 23 (M4, measurements/a3/P*.json m4_streams): the smallest whole hour at or above the 95th-percentile gap of
# every stream of the family with at least 2,000 events on the rich phones; bucketed families: bucket width + 10 %.
MAX_GAP_S = {"device_events": 3600, "connectivity": 3600, "locations": 3600, "wifi": 3600, "cell": 3600,
             "sensors": 3960, "network_usage": 7920}
OBSERVING_FAMILIES = tuple(sorted(MAX_GAP_S))
COVERAGE_SEMANTICS = ("event_instant", "interval_start", "interval_end", "aggregate_bucket")
OBSERVED_HOUR_MINUTES = 50
INFER_WINDOW = timedelta(hours=24)
FAR_END = datetime(9999, 12, 31, tzinfo=timezone.utc)
ON_VALUES = frozenset({"on", "power on", "poweron", "powered on", "boot", "start"})
OFF_VALUES = frozenset({"off", "power off", "poweroff", "powered off", "shutdown", "shut down"})
BAND_PRIORITY = ("after_extraction", "powered_off", "powered_off_inferred", "outside_selection", "not_selected")

UI_COPY = {"no_data": "No data", "data_no_interaction": "Phone recording, no use seen",
           "powered_off": "Switched off", "powered_off_inferred": "Switched off (inferred)",
           "after_extraction": "After the extraction", "outside_selection": "Outside what the production selected",
           "not_selected": "Outside what the production selected", "interaction": "In use"}
NO_SELECTION_STATED = "The production does not state a selection."


def extraction_start(conn, extraction_id):
    return conn.execute(text(
        "SELECT min(instant) FROM phone_timestamps WHERE extraction_id = :e AND owner_kind = 'skeleton' AND "
        "field_name = 'DeviceInfoExtractionStartDateTime' AND instant IS NOT NULL"), {"e": extraction_id}).scalar()


def _merge(points, max_gap):
    """points: sorted [(start, end)]; returns [(start, end, count)]."""
    out = []
    gap = timedelta(seconds=max_gap)
    for s, e in points:
        if out and s - out[-1][1] <= gap:
            ps, pe, n = out[-1]
            out[-1] = (ps, max(pe, e), n + 1)
        else:
            out.append((s, e, 1))
    return out


def _power_state(record_type, facts):
    f = (facts or {}).get("fields") or {}
    if record_type == "PoweringEvent":
        v = activity._first(f.get("Event"))
    else:
        if activity._first(f.get("EventType")) != "PowerEvent":
            return None
        v = activity._first(f.get("Value"))
    v = (v or "").strip().lower()
    return "on" if v in ON_VALUES else ("off" if v in OFF_VALUES else None)


def compute(conn, extraction_id) -> dict:
    """Rebuild bands and rollup for one extraction from its activity events (no commit)."""
    st = activity.current_generation(conn, extraction_id)
    if st is None:
        return {"status": "not_interpreted"}
    case_id = st.case_id
    conn.execute(text("DELETE FROM pol_availability_band WHERE extraction_id = :e"), {"e": extraction_id})
    conn.execute(text("DELETE FROM pol_hourly_rollup WHERE extraction_id = :e"), {"e": extraction_id})
    stats = defaultdict(int)
    capable = {r[0] for r in conn.execute(text(
        "SELECT DISTINCT stream_key FROM pol_activity_event WHERE extraction_id = :e AND activity_class = 'interaction' "
        "AND actor = 'owner'"), {"e": extraction_id})}
    bands = []
    segs_all, segs_capable = [], []
    cur_key, cur_family, pts = None, None, []

    def close():
        if cur_key is None:
            return
        for s, e, n in _merge(pts, MAX_GAP_S[cur_family]):
            bands.append({"family": cur_family, "stream_key": cur_key, "band": "observed", "start_utc": s, "end_utc": e,
                          "event_count": n, "inferred": False, "interaction_capable": cur_key in capable,
                          "computed_from": {"max_gap_s": MAX_GAP_S[cur_family]}})
            segs_all.append((s, e))
            if cur_key in capable:
                segs_capable.append((s, e))
            stats["observed_segments"] += 1
    for fam, key, s, e in conn.execute(text(
            "SELECT family, stream_key, instant_utc, coalesce(end_utc, instant_utc) FROM pol_activity_event WHERE "
            "extraction_id = :e AND family = ANY(:f) AND time_semantics = ANY(:sem) ORDER BY stream_key, instant_utc"
            ).execution_options(stream_results=True, yield_per=20000),
            {"e": extraction_id, "f": list(OBSERVING_FAMILIES), "sem": list(COVERAGE_SEMANTICS)}):
        if key != cur_key:
            close()
            cur_key, cur_family, pts = key, fam, []
        pts.append((s, max(s, e)))
    close()
    segs_all.sort()
    # power (5.3 step 5)
    last_off = None
    for inst, rtype, facts in conn.execute(text(
            "SELECT instant_utc, record_type, match_facts FROM pol_activity_event WHERE extraction_id = :e AND "
            "family = 'power' ORDER BY instant_utc"), {"e": extraction_id}):
        state = _power_state(rtype, facts)
        if state == "off":
            last_off = inst
            stats["power_off_events"] += 1
        elif state == "on":
            stats["power_on_events"] += 1
            if last_off is not None and inst - last_off <= INFER_WINDOW:
                bands.append({"family": "power", "stream_key": None, "band": "powered_off", "start_utc": last_off,
                              "end_utc": inst, "event_count": 2, "inferred": False, "interaction_capable": False,
                              "computed_from": {"rule": "off_then_on"}})
                stats["powered_off"] += 1
            else:
                before = [e for s, e in segs_all if e < inst]
                if before:
                    bands.append({"family": "power", "stream_key": None, "band": "powered_off_inferred",
                                  "start_utc": max(before), "end_utc": inst, "event_count": 1, "inferred": True,
                                  "interaction_capable": False,
                                  "computed_from": {"rule": "on_without_off_in_24h",
                                                    "from": "end of the last observed segment before it"}})
                    stats["powered_off_inferred"] += 1
                else:
                    stats["power_on_without_earlier_observation"] += 1
            last_off = None
    start = extraction_start(conn, extraction_id)
    if start is not None:
        bands.append({"family": "all", "stream_key": None, "band": "after_extraction", "start_utc": start,
                      "end_utc": FAR_END, "event_count": 0, "inferred": False, "interaction_capable": False,
                      "computed_from": {"rule": "DeviceInfoExtractionStartDateTime"}})
        stats["events_after_extraction_start"] = conn.execute(text(
            "UPDATE pol_activity_event SET attribution_flags = array_append(attribution_flags, 'after_extraction_time') "
            "WHERE extraction_id = :e AND instant_utc > :s AND NOT ('after_extraction_time' = ANY(attribution_flags))"),
            {"e": extraction_id, "s": start}).rowcount
    else:
        stats["extraction_start_not_in_report"] = 1
    stats["selection_stated"] = 0  # 5.3 step 2: no production states a selection (M11); NO_SELECTION_STATED is shown
    if bands:
        conn.execute(text(
            "INSERT INTO pol_availability_band (case_id, extraction_id, family, stream_key, band, start_utc, end_utc, "
            "event_count, inferred, interaction_capable, computed_from) VALUES (:c, :e, :family, :stream_key, :band, "
            ":start_utc, :end_utc, :event_count, :inferred, :interaction_capable, CAST(:cf AS jsonb))"),
            [dict(b, c=case_id, e=extraction_id, cf=json.dumps(b["computed_from"])) for b in bands])
    _rollup(conn, extraction_id, case_id, segs_all, segs_capable, bands)
    stats["bands"] = len(bands)
    return dict(stats)


def _minutes_by_hour(segs):
    """Union of segments, as minutes per UTC hour."""
    out = defaultdict(float)
    merged = []
    for s, e in sorted(segs):
        if e <= s:
            continue
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    for s, e in merged:
        h = s.replace(minute=0, second=0, microsecond=0)
        while h < e:
            nxt = h + timedelta(hours=1)
            out[h] += (min(e, nxt) - max(s, h)).total_seconds() / 60.0
            h = nxt
    return out


def _rollup(conn, extraction_id, case_id, segs_all, segs_capable, bands):
    conn.execute(text(
        "INSERT INTO pol_hourly_rollup (extraction_id, case_id, hour_utc, interaction_strong, interaction_moderate, "
        "interaction_weak, device_state, passive, physical) "
        "SELECT :e, :c, date_trunc('hour', instant_utc AT TIME ZONE 'UTC') AT TIME ZONE 'UTC', "
        " count(*) FILTER (WHERE activity_class = 'interaction' AND counts_for = 'owner' AND strength = 'strong'), "
        " count(*) FILTER (WHERE activity_class = 'interaction' AND counts_for = 'owner' AND strength = 'moderate'), "
        " count(*) FILTER (WHERE activity_class = 'interaction' AND counts_for = 'owner' AND strength = 'weak'), "
        " count(*) FILTER (WHERE activity_class = 'device_state' AND counts_for = 'owner'), "
        " count(*) FILTER (WHERE activity_class = 'passive'), count(*) FILTER (WHERE physical) "
        "FROM pol_activity_event_v WHERE extraction_id = :e GROUP BY 3"), {"e": extraction_id, "c": case_id})
    allm, capm = _minutes_by_hour(segs_all), _minutes_by_hour(segs_capable)
    rows = [{"e": extraction_id, "c": case_id, "h": h, "m": int(round(min(60, allm[h]))),
             "cm": int(round(min(60, capm.get(h, 0))))} for h in allm]
    for b in bands:
        if b["band"] in ("powered_off", "powered_off_inferred"):
            h = b["start_utc"].replace(minute=0, second=0, microsecond=0)
            if h < b["start_utc"]:
                h += timedelta(hours=1)
            while h + timedelta(hours=1) <= b["end_utc"]:
                rows.append({"e": extraction_id, "c": case_id, "h": h, "m": None, "cm": None, "band": b["band"]})
                h += timedelta(hours=1)
    if rows:
        conn.execute(text(
            "INSERT INTO pol_hourly_rollup (extraction_id, case_id, hour_utc, observed_minutes, observed_capable_minutes, "
            "band) VALUES (:e, :c, :h, coalesce(:m, 0), coalesce(:cm, 0), :band) ON CONFLICT (extraction_id, hour_utc) "
            "DO UPDATE SET observed_minutes = CASE WHEN :m IS NULL THEN pol_hourly_rollup.observed_minutes ELSE "
            "EXCLUDED.observed_minutes END, observed_capable_minutes = CASE WHEN :cm IS NULL THEN "
            "pol_hourly_rollup.observed_capable_minutes ELSE EXCLUDED.observed_capable_minutes END, "
            "band = coalesce(EXCLUDED.band, pol_hourly_rollup.band)"),
            [dict({"band": None}, **r) for r in rows])


# ---- reading ------------------------------------------------------------------------------------------------------

def bands(conn, extraction_id, start, end, kinds=None):
    q = ("SELECT family, stream_key, band, start_utc, end_utc, event_count, inferred, interaction_capable "
         "FROM pol_availability_band WHERE extraction_id = :e AND start_utc < :b AND end_utc > :a")
    rows = conn.execute(text(q + " ORDER BY start_utc"), {"e": extraction_id, "a": start, "b": end}).mappings().all()
    return [dict(r) for r in rows if kinds is None or r["band"] in kinds]


def hour_states(conn, extraction_id, start, end) -> list:
    """[{hour_utc, state, counts, observed_minutes, observed_capable_minutes}] for every UTC hour in [start, end)."""
    start = start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    # the nine columns read below, as tuples (a Pattern grid reads 20,000 hours; whole rows as dicts cost 0.3 s)
    roll = {r[0]: tuple(v or 0 for v in r[1:]) for r in conn.execute(text(
        "SELECT hour_utc, interaction_strong, interaction_moderate, interaction_weak, device_state, passive, physical, "
        "observed_minutes, observed_capable_minutes FROM pol_hourly_rollup WHERE extraction_id = :e AND hour_utc >= :a "
        "AND hour_utc < :b"), {"e": extraction_id, "a": start, "b": end})}
    empty = (0,) * 8
    whole = bands(conn, extraction_id, start, end, kinds=BAND_PRIORITY)
    # the highest-priority band wholly covering each hour: each band marks the hours it covers (hour k spans
    # start + k h to start + (k + 1) h), so the cost is the hours covered, not hours x bands (6.5 million band tests
    # for a 670-day grid)
    one = timedelta(hours=1)
    n_hours = -((start - end) // one)
    rank = {name: i for i, name in enumerate(BAND_PRIORITY)}
    best = {}
    for b in whole:
        i = rank[b["band"]]
        k0 = max(0, -((start - b["start_utc"]) // one))  # first hour starting at or after the band's start
        k1 = min(n_hours, (b["end_utc"] - start) // one)  # hours ending at or before the band's end
        for k in range(k0, k1):
            if best.get(k, len(BAND_PRIORITY)) > i:
                best[k] = i
    out = []
    h = start
    k = 0
    while h < end:
        strong, moderate, weak, device_state, passive, physical, observed, capable = roll.get(h, empty)
        state = BAND_PRIORITY[best[k]] if k in best else None
        k += 1
        if state is None:
            if strong + moderate + weak > 0:
                state = "interaction"
            elif observed >= OBSERVED_HOUR_MINUTES:
                state = "data_no_interaction"
            else:
                state = "no_data"
        out.append({"hour_utc": h, "state": state,
                    "counts": {"strong": strong, "moderate": moderate, "weak": weak, "device_state": device_state,
                               "passive": passive, "physical": physical},
                    "observed_minutes": observed, "observed_capable_minutes": capable})
        h += one
    return out


def window_pieces(conn, extraction_id, start, end) -> list:
    """5.3 step 7: the window split at band boundaries; each piece carries its state (a band, ``observed`` or
    ``no_data``), the streams observing it and whether any of them can show a person's use."""
    bs = bands(conn, extraction_id, start, end)
    cuts = {start, end}
    for b in bs:
        for t in (b["start_utc"], b["end_utc"]):
            if start < t < end:
                cuts.add(t)
    cuts = sorted(cuts)
    pieces = []
    for a, b in zip(cuts, cuts[1:]):
        cover = [x for x in bs if x["start_utc"] <= a and x["end_utc"] >= b and x["end_utc"] > x["start_utc"]]
        state = None
        for name in BAND_PRIORITY:
            if any(x["band"] == name for x in cover):
                state = name
                break
        streams = sorted({x["stream_key"] for x in cover if x["band"] == "observed"})
        capable = any(x["interaction_capable"] for x in cover if x["band"] == "observed")
        if state is None:
            state = "observed" if streams else "no_data"
        piece = {"start": a, "end": b, "state": state, "streams": streams if state == "observed" else [],
                 "interaction_capable": capable if state == "observed" else False}
        if pieces and pieces[-1]["state"] == piece["state"] and pieces[-1]["streams"] == piece["streams"] \
                and pieces[-1]["end"] == a:
            pieces[-1]["end"] = b
        else:
            pieces.append(piece)
    return pieces


def streams(conn, extraction_id) -> list:
    """Every stream with its family, first, last, event count, max gap and whether it can show a person's use."""
    capable = {r[0] for r in conn.execute(text(
        "SELECT DISTINCT stream_key FROM pol_activity_event WHERE extraction_id = :e AND activity_class = 'interaction' "
        "AND actor = 'owner'"), {"e": extraction_id})}
    out = []
    for key, fam, first, last, n in conn.execute(text(
            "SELECT stream_key, family, min(instant_utc), max(coalesce(end_utc, instant_utc)), count(*) FROM "
            "pol_activity_event WHERE extraction_id = :e AND time_semantics = ANY(:sem) GROUP BY 1, 2 ORDER BY 2, 1"),
            {"e": extraction_id, "sem": list(COVERAGE_SEMANTICS)}):
        out.append({"stream_key": key, "family": fam, "first": first, "last": last, "events": n,
                    "max_gap_s": MAX_GAP_S.get(fam), "establishes_observation": fam in MAX_GAP_S,
                    "interaction_capable": key in capable})
    return out


def install():
    activity.register_after_activity(compute)
