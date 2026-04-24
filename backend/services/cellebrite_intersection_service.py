"""
Cellebrite Intersection Detection Service (Phase 4)

Five on-demand detection methods for finding cross-device co-occurrence signals
in ingested Cellebrite data:

  1. spatial     — devices within X metres of each other within Y seconds
  2. cell_tower  — devices registered to the same tower around the same time
  3. wifi        — devices associated with the same BSSID/SSID around the same time
  4. comm_hub    — multiple devices communicated with the same 3rd party within a window
  5. convoy      — sustained co-location (builds on spatial)

Each method is a pure read-only function against Neo4j. Results are returned
in a uniform shape for the frontend to render.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from services.neo4j_service import neo4j_service


# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two (lat, lon) in metres."""
    R = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _parse_ts(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _match_id(method: str, devices: List[str], start: datetime) -> str:
    """Stable match ID for deduplication across repeat runs."""
    payload = f"{method}|{'|'.join(sorted(devices))}|{start.isoformat()}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _empty_result(method: str, params: dict, reason: Optional[str] = None) -> dict:
    return {
        "method": method,
        "matches": [],
        "params_used": params,
        "reason": reason,
    }


# ----------------------------------------------------------------------------
# Data loaders
# ----------------------------------------------------------------------------


def _load_events(
    case_id: str,
    report_keys: Optional[List[str]],
    start_date: Optional[str],
    end_date: Optional[str],
    only_geolocated: bool = True,
    event_types: Optional[List[str]] = None,
) -> List[dict]:
    """Load events from neo4j_service for use by the sweep-based methods."""
    data = neo4j_service.get_cellebrite_events(
        case_id=case_id,
        report_keys=report_keys,
        event_types=event_types,
        start_date=start_date,
        end_date=end_date,
        only_geolocated=only_geolocated,
        limit=20000,  # generous cap
        offset=0,
    )
    return data.get("events") or []


# ----------------------------------------------------------------------------
# Method 1: Spatial co-presence
# ----------------------------------------------------------------------------


def detect_spatial(
    case_id: str,
    report_keys: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_distance_m: float = 250.0,
    max_time_delta_s: float = 600.0,
) -> dict:
    """Sweep all geolocated events ordered by time; for each event find cross-device
    neighbours within the given time window and spatial radius.
    """
    params = {
        "max_distance_m": max_distance_m,
        "max_time_delta_s": max_time_delta_s,
    }
    events = _load_events(case_id, report_keys, start_date, end_date, only_geolocated=True)
    # Normalise events: require lat/lon/timestamp/device
    items = []
    for e in events:
        ts = _parse_ts(e.get("timestamp"))
        if (
            ts is None
            or e.get("latitude") is None
            or e.get("longitude") is None
            or not e.get("device_report_key")
        ):
            continue
        items.append({
            "t": ts,
            "t_sec": ts.timestamp(),
            "lat": float(e["latitude"]),
            "lon": float(e["longitude"]),
            "device": e["device_report_key"],
            "event_id": e.get("id") or e.get("node_key"),
            "label": e.get("label"),
            "timestamp": e.get("timestamp"),
        })
    items.sort(key=lambda x: x["t_sec"])

    # Group distinct device count
    if len({it["device"] for it in items}) < 2:
        return _empty_result("spatial", params, "Need at least 2 devices with geolocated events")

    matches: List[dict] = []
    # Sweep line — for each event, scan forward while time diff ≤ window
    n = len(items)
    seen_group_keys = set()  # dedupe by (sorted devices + rounded time)
    for i, a in enumerate(items):
        j = i + 1
        cluster = [a]
        cluster_devices = {a["device"]}
        while j < n and (items[j]["t_sec"] - a["t_sec"]) <= max_time_delta_s:
            b = items[j]
            if b["device"] != a["device"] and _haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) <= max_distance_m:
                cluster.append(b)
                cluster_devices.add(b["device"])
            j += 1
        if len(cluster_devices) >= 2:
            devices = sorted(cluster_devices)
            group_key = (tuple(devices), int(a["t_sec"] // max(max_time_delta_s, 1)))
            if group_key in seen_group_keys:
                continue
            seen_group_keys.add(group_key)
            start = min(c["t"] for c in cluster)
            end = max(c["t"] for c in cluster)
            center_lat = sum(c["lat"] for c in cluster) / len(cluster)
            center_lon = sum(c["lon"] for c in cluster) / len(cluster)
            max_pair_dist = max(
                _haversine_m(x["lat"], x["lon"], y["lat"], y["lon"])
                for idx1, x in enumerate(cluster) for y in cluster[idx1+1:]
            ) if len(cluster) > 1 else 0.0
            score = max(0.0, 1.0 - (max_pair_dist / max_distance_m))
            matches.append({
                "id": _match_id("spatial", devices, start),
                "devices": devices,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "score": round(score, 3),
                "evidence": [
                    {
                        "event_id": c["event_id"],
                        "device_report_key": c["device"],
                        "timestamp": c["timestamp"],
                        "label": c["label"],
                        "latitude": c["lat"],
                        "longitude": c["lon"],
                    }
                    for c in cluster
                ],
                "summary": f"{len(devices)} devices within {int(max_pair_dist)} m @ {start.isoformat()}",
                "center": {"lat": center_lat, "lon": center_lon},
            })

    return {"method": "spatial", "matches": matches, "params_used": params}


# ----------------------------------------------------------------------------
# Method 2: Shared cell tower
# ----------------------------------------------------------------------------


def detect_cell_tower(
    case_id: str,
    report_keys: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_time_delta_s: float = 900.0,
) -> dict:
    params = {"max_time_delta_s": max_time_delta_s}
    rk_filter = ""
    query_params: Dict[str, Any] = {"case_id": case_id}
    if report_keys:
        rk_filter = "AND n.cellebrite_report_key IN $report_keys"
        query_params["report_keys"] = list(report_keys)
    if start_date:
        rk_filter += " AND n.timestamp >= $start_date"
        query_params["start_date"] = start_date
    if end_date:
        rk_filter += " AND n.timestamp <= $end_date"
        query_params["end_date"] = end_date

    # Group towers by identity tuple
    groups: Dict[tuple, List[dict]] = defaultdict(list)
    with neo4j_service._driver.session() as session:
        r = session.run(
            f"""
            MATCH (n:CellTower {{case_id:$case_id, source_type:'cellebrite'}})
            WHERE n.timestamp IS NOT NULL {rk_filter}
            RETURN n.cell_id AS cid, n.mcc AS mcc, n.mnc AS mnc, n.lac AS lac,
                   n.timestamp AS ts, n.cellebrite_report_key AS rk,
                   n.latitude AS lat, n.longitude AS lon, n.key AS key
            """,
            query_params,
        )
        for rec in r:
            key = (rec["cid"], rec["mcc"], rec["mnc"], rec["lac"])
            if key[0] is None:
                continue
            ts = _parse_ts(rec["ts"])
            if ts is None:
                continue
            groups[key].append({
                "t": ts, "t_sec": ts.timestamp(),
                "device": rec["rk"], "lat": rec["lat"], "lon": rec["lon"],
                "event_id": rec["key"], "label": f"Cell {key[0]}",
                "timestamp": rec["ts"],
            })

    if not groups:
        return _empty_result("cell_tower", params, "No CellTower events in selection")

    matches = []
    for key, pings in groups.items():
        pings.sort(key=lambda p: p["t_sec"])
        # Sweep: any window of <= max_time_delta_s containing >= 2 devices
        n = len(pings)
        for i, a in enumerate(pings):
            cluster = [a]
            devs = {a["device"]}
            j = i + 1
            while j < n and (pings[j]["t_sec"] - a["t_sec"]) <= max_time_delta_s:
                if pings[j]["device"] != a["device"]:
                    cluster.append(pings[j])
                    devs.add(pings[j]["device"])
                j += 1
            if len(devs) >= 2:
                devices = sorted(devs)
                start = min(c["t"] for c in cluster)
                end = max(c["t"] for c in cluster)
                lat = next((c["lat"] for c in cluster if c["lat"] is not None), None)
                lon = next((c["lon"] for c in cluster if c["lon"] is not None), None)
                matches.append({
                    "id": _match_id("cell_tower", devices, start),
                    "devices": devices,
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                    "score": round(1.0 - (end - start).total_seconds() / max(max_time_delta_s, 1), 3),
                    "evidence": [{
                        "event_id": c["event_id"],
                        "device_report_key": c["device"],
                        "timestamp": c["timestamp"],
                        "label": c["label"],
                        "latitude": c["lat"],
                        "longitude": c["lon"],
                    } for c in cluster],
                    "summary": f"{len(devices)} devices on cell {key[0]} @ {start.isoformat()}",
                    "center": {"lat": lat, "lon": lon} if lat and lon else None,
                })

    # Dedupe by (devices, rounded start)
    seen = set()
    out = []
    for m in matches:
        k = (tuple(m["devices"]), m["start_time"][:16])
        if k in seen:
            continue
        seen.add(k)
        out.append(m)
    return {"method": "cell_tower", "matches": out, "params_used": params}


# ----------------------------------------------------------------------------
# Method 3: Shared WiFi
# ----------------------------------------------------------------------------


def detect_wifi(
    case_id: str,
    report_keys: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_time_delta_s: float = 1800.0,
) -> dict:
    params = {"max_time_delta_s": max_time_delta_s}
    rk_filter = ""
    query_params: Dict[str, Any] = {"case_id": case_id}
    if report_keys:
        rk_filter = "AND n.cellebrite_report_key IN $report_keys"
        query_params["report_keys"] = list(report_keys)
    if start_date:
        rk_filter += " AND n.timestamp >= $start_date"
        query_params["start_date"] = start_date
    if end_date:
        rk_filter += " AND n.timestamp <= $end_date"
        query_params["end_date"] = end_date

    groups: Dict[str, List[dict]] = defaultdict(list)
    with neo4j_service._driver.session() as session:
        r = session.run(
            f"""
            MATCH (n:WirelessNetwork {{case_id:$case_id, source_type:'cellebrite'}})
            WHERE n.timestamp IS NOT NULL {rk_filter}
            RETURN n.bssid AS bssid, n.ssid AS ssid, n.timestamp AS ts,
                   n.cellebrite_report_key AS rk, n.key AS key
            """,
            query_params,
        )
        for rec in r:
            key = rec["bssid"] or rec["ssid"]
            if not key:
                continue
            ts = _parse_ts(rec["ts"])
            if ts is None:
                continue
            groups[key].append({
                "t": ts, "t_sec": ts.timestamp(),
                "device": rec["rk"],
                "event_id": rec["key"],
                "label": f"WiFi {rec['ssid'] or rec['bssid']}",
                "timestamp": rec["ts"],
            })

    if not groups:
        return _empty_result("wifi", params, "No timestamped WiFi events in selection")

    matches = []
    for key, assocs in groups.items():
        assocs.sort(key=lambda p: p["t_sec"])
        n = len(assocs)
        for i, a in enumerate(assocs):
            cluster = [a]
            devs = {a["device"]}
            j = i + 1
            while j < n and (assocs[j]["t_sec"] - a["t_sec"]) <= max_time_delta_s:
                if assocs[j]["device"] != a["device"]:
                    cluster.append(assocs[j])
                    devs.add(assocs[j]["device"])
                j += 1
            if len(devs) >= 2:
                devices = sorted(devs)
                start = min(c["t"] for c in cluster)
                end = max(c["t"] for c in cluster)
                matches.append({
                    "id": _match_id("wifi", devices, start),
                    "devices": devices,
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                    "score": round(1.0 - (end - start).total_seconds() / max(max_time_delta_s, 1), 3),
                    "evidence": [{
                        "event_id": c["event_id"],
                        "device_report_key": c["device"],
                        "timestamp": c["timestamp"],
                        "label": c["label"],
                        "latitude": None,
                        "longitude": None,
                    } for c in cluster],
                    "summary": f"{len(devices)} devices on WiFi {key} @ {start.isoformat()}",
                    "center": None,
                })

    return {"method": "wifi", "matches": matches, "params_used": params}


# ----------------------------------------------------------------------------
# Method 4: Communication hub
# ----------------------------------------------------------------------------


def detect_comm_hub(
    case_id: str,
    report_keys: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    time_window_s: float = 3600.0,
    min_devices: int = 2,
) -> dict:
    """Multiple devices talking to the same counterpart Person within a window."""
    params = {"time_window_s": time_window_s, "min_devices": min_devices}
    rk_filter = ""
    query_params: Dict[str, Any] = {"case_id": case_id}
    if report_keys:
        rk_filter = "AND n.cellebrite_report_key IN $report_keys"
        query_params["report_keys"] = list(report_keys)
    if start_date:
        rk_filter += " AND n.timestamp >= $start_date"
        query_params["start_date"] = start_date
    if end_date:
        rk_filter += " AND n.timestamp <= $end_date"
        query_params["end_date"] = end_date

    # Collect tuples (counterpart_key, counterpart_name, device, ts, label, event_id)
    interactions: List[dict] = []
    with neo4j_service._driver.session() as session:
        # Calls: owner direction not always reliable — collect every counterparty that isn't the owner
        r = session.run(
            f"""
            MATCH (n:PhoneCall {{case_id:$case_id, source_type:'cellebrite'}})
            WHERE n.timestamp IS NOT NULL {rk_filter}
            OPTIONAL MATCH (src:Person)-[:CALLED]->(n)
            OPTIONAL MATCH (n)-[:CALLED_TO]->(dst:Person)
            WITH n, src, dst
            RETURN n.timestamp AS ts, n.key AS key, n.cellebrite_report_key AS rk,
                   src.key AS src_key, src.name AS src_name, src.is_phone_owner AS src_owner,
                   dst.key AS dst_key, dst.name AS dst_name, dst.is_phone_owner AS dst_owner
            """,
            query_params,
        )
        for rec in r:
            ts = _parse_ts(rec["ts"])
            if not ts:
                continue
            # Counterpart = whichever side isn't the phone owner
            if rec["src_owner"] and rec["dst_key"]:
                counter_key, counter_name = rec["dst_key"], rec["dst_name"]
            elif rec["dst_owner"] and rec["src_key"]:
                counter_key, counter_name = rec["src_key"], rec["src_name"]
            else:
                # Fallback: prefer dst if exists
                counter_key = rec["dst_key"] or rec["src_key"]
                counter_name = rec["dst_name"] or rec["src_name"]
            if not counter_key or not rec["rk"]:
                continue
            interactions.append({
                "counter_key": counter_key,
                "counter_name": counter_name or counter_key,
                "device": rec["rk"],
                "t": ts, "t_sec": ts.timestamp(),
                "event_id": rec["key"], "label": "Call",
                "timestamp": rec["ts"],
            })

        # Messages
        r = session.run(
            f"""
            MATCH (n:Communication {{case_id:$case_id, source_type:'cellebrite'}})
            WHERE n.body IS NOT NULL AND n.timestamp IS NOT NULL {rk_filter}
            OPTIONAL MATCH (sender:Person)-[:SENT_MESSAGE]->(n)
            OPTIONAL MATCH (n)-[:PART_OF]->(chat:Communication)
            OPTIONAL MATCH (part:Person)-[:PARTICIPATED_IN]->(chat)
            WITH n, sender, collect(DISTINCT part) AS participants
            RETURN n.timestamp AS ts, n.key AS key, n.cellebrite_report_key AS rk,
                   sender.key AS sender_key, sender.name AS sender_name,
                   sender.is_phone_owner AS sender_owner,
                   [p IN participants | {{key: p.key, name: p.name, is_owner: p.is_phone_owner}}] AS participants
            """,
            query_params,
        )
        for rec in r:
            ts = _parse_ts(rec["ts"])
            if not ts or not rec["rk"]:
                continue
            # Counterpart: if sender is owner, pick first non-owner participant; else sender
            counter_key = None
            counter_name = None
            if rec["sender_owner"]:
                for p in rec["participants"] or []:
                    if p and p.get("key") and not p.get("is_owner"):
                        counter_key = p["key"]
                        counter_name = p.get("name") or counter_key
                        break
            else:
                counter_key = rec["sender_key"]
                counter_name = rec["sender_name"] or counter_key
            if not counter_key:
                continue
            interactions.append({
                "counter_key": counter_key,
                "counter_name": counter_name or counter_key,
                "device": rec["rk"],
                "t": ts, "t_sec": ts.timestamp(),
                "event_id": rec["key"], "label": "Message",
                "timestamp": rec["ts"],
            })

        # Emails
        r = session.run(
            f"""
            MATCH (n:Email {{case_id:$case_id, source_type:'cellebrite'}})
            WHERE n.timestamp IS NOT NULL {rk_filter}
            OPTIONAL MATCH (src:Person)-[:EMAILED]->(n)
            OPTIONAL MATCH (n)-[:SENT_TO]->(dst:Person)
            RETURN n.timestamp AS ts, n.key AS key, n.cellebrite_report_key AS rk,
                   src.key AS src_key, src.name AS src_name, src.is_phone_owner AS src_owner,
                   dst.key AS dst_key, dst.name AS dst_name, dst.is_phone_owner AS dst_owner
            """,
            query_params,
        )
        for rec in r:
            ts = _parse_ts(rec["ts"])
            if not ts:
                continue
            if rec["src_owner"] and rec["dst_key"]:
                counter_key, counter_name = rec["dst_key"], rec["dst_name"]
            elif rec["dst_owner"] and rec["src_key"]:
                counter_key, counter_name = rec["src_key"], rec["src_name"]
            else:
                counter_key = rec["dst_key"] or rec["src_key"]
                counter_name = rec["dst_name"] or rec["src_name"]
            if not counter_key or not rec["rk"]:
                continue
            interactions.append({
                "counter_key": counter_key,
                "counter_name": counter_name or counter_key,
                "device": rec["rk"],
                "t": ts, "t_sec": ts.timestamp(),
                "event_id": rec["key"], "label": "Email",
                "timestamp": rec["ts"],
            })

    if not interactions:
        return _empty_result("comm_hub", params, "No interactions in selection")

    # For each counterpart, sweep time windows
    by_counter: Dict[str, List[dict]] = defaultdict(list)
    for it in interactions:
        by_counter[it["counter_key"]].append(it)

    matches = []
    for counter_key, items in by_counter.items():
        items.sort(key=lambda x: x["t_sec"])
        n = len(items)
        for i, a in enumerate(items):
            cluster = [a]
            devs = {a["device"]}
            j = i + 1
            while j < n and (items[j]["t_sec"] - a["t_sec"]) <= time_window_s:
                if items[j]["device"] != a["device"]:
                    cluster.append(items[j])
                    devs.add(items[j]["device"])
                j += 1
            if len(devs) >= min_devices:
                devices = sorted(devs)
                start = min(c["t"] for c in cluster)
                end = max(c["t"] for c in cluster)
                matches.append({
                    "id": _match_id("comm_hub", devices + [counter_key], start),
                    "devices": devices,
                    "counterpart": {"key": counter_key, "name": a["counter_name"]},
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                    "score": round(min(1.0, len(devs) / max(min_devices, 1) * 0.5), 3),
                    "evidence": [{
                        "event_id": c["event_id"],
                        "device_report_key": c["device"],
                        "timestamp": c["timestamp"],
                        "label": c["label"],
                        "latitude": None,
                        "longitude": None,
                    } for c in cluster],
                    "summary": f"{len(devices)} devices ↔ {a['counter_name']} in ≤ {int(time_window_s/60)} min",
                    "center": None,
                })

    # Dedupe
    seen = set()
    out = []
    for m in matches:
        k = (tuple(m["devices"]), m["counterpart"]["key"], m["start_time"][:16])
        if k in seen:
            continue
        seen.add(k)
        out.append(m)
    return {"method": "comm_hub", "matches": out, "params_used": params}


# ----------------------------------------------------------------------------
# Method 5: Convoy
# ----------------------------------------------------------------------------


def detect_convoy(
    case_id: str,
    report_keys: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_distance_m: float = 500.0,
    min_duration_s: float = 1800.0,
    min_samples: int = 5,
) -> dict:
    """Extend spatial detection: require the same device set to stay co-located
    across >= min_samples points spanning >= min_duration_s.
    """
    params = {
        "max_distance_m": max_distance_m,
        "min_duration_s": min_duration_s,
        "min_samples": min_samples,
    }
    # Run spatial with a generous time window first
    spatial = detect_spatial(
        case_id=case_id,
        report_keys=report_keys,
        start_date=start_date,
        end_date=end_date,
        max_distance_m=max_distance_m,
        max_time_delta_s=600.0,
    )
    if not spatial.get("matches"):
        return _empty_result("convoy", params, "No spatial co-presences as base")

    # Group spatial matches by identical device set + temporal chaining
    by_devices: Dict[tuple, List[dict]] = defaultdict(list)
    for m in spatial["matches"]:
        by_devices[tuple(m["devices"])].append(m)

    convoys = []
    for devices, cluster_list in by_devices.items():
        cluster_list.sort(key=lambda m: m["start_time"])
        if len(cluster_list) < min_samples:
            continue
        start_t = _parse_ts(cluster_list[0]["start_time"])
        end_t = _parse_ts(cluster_list[-1]["end_time"])
        if not start_t or not end_t:
            continue
        duration = (end_t - start_t).total_seconds()
        if duration < min_duration_s:
            continue
        # Aggregate evidence (up to 50 points)
        evidence = []
        for m in cluster_list[:50]:
            evidence.extend(m.get("evidence") or [])
        # Centre = average of centres
        valid_centers = [m["center"] for m in cluster_list if m.get("center")]
        center = None
        if valid_centers:
            center = {
                "lat": sum(c["lat"] for c in valid_centers) / len(valid_centers),
                "lon": sum(c["lon"] for c in valid_centers) / len(valid_centers),
            }
        convoys.append({
            "id": _match_id("convoy", list(devices), start_t),
            "devices": list(devices),
            "start_time": start_t.isoformat(),
            "end_time": end_t.isoformat(),
            "score": round(min(1.0, len(cluster_list) / (min_samples * 2)), 3),
            "evidence": evidence[:50],
            "summary": f"Convoy of {len(devices)} devices, {len(cluster_list)} samples, {int(duration/60)} min",
            "center": center,
        })

    return {"method": "convoy", "matches": convoys, "params_used": params}


# ----------------------------------------------------------------------------
# Dispatcher
# ----------------------------------------------------------------------------


METHOD_REGISTRY = {
    "spatial": detect_spatial,
    "cell_tower": detect_cell_tower,
    "wifi": detect_wifi,
    "comm_hub": detect_comm_hub,
    "convoy": detect_convoy,
}


def run_methods(
    case_id: str,
    methods: List[str],
    report_keys: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    params: Optional[Dict[str, Dict[str, Any]]] = None,
) -> dict:
    """Run one or more detection methods and return combined results."""
    params = params or {}
    results = []
    for m in methods:
        fn = METHOD_REGISTRY.get(m)
        if not fn:
            results.append({
                "method": m,
                "matches": [],
                "params_used": {},
                "reason": f"Unknown method '{m}'",
            })
            continue
        method_params = params.get(m, {})
        try:
            result = fn(
                case_id=case_id,
                report_keys=report_keys,
                start_date=start_date,
                end_date=end_date,
                **method_params,
            )
        except TypeError as e:
            result = {
                "method": m,
                "matches": [],
                "params_used": method_params,
                "reason": f"Invalid params: {e}",
            }
        results.append(result)
    return {"results": results}
