"""
Cellebrite Neo4j analytics service.

This module ports the Cellebrite query surface from the latest main branch into
OWL's split Neo4j service architecture. It deliberately contains only
Cellebrite/report query helpers; the legacy monolithic neo4j_service.py stays a
thin facade over focused domain services.
"""

from __future__ import annotations

import base64
import json
import logging
import math
from typing import Any, Dict, List, Optional, Set, Tuple

from services.neo4j.driver import driver

logger = logging.getLogger(__name__)


def _normalize_date_bound(value: Optional[str]) -> Optional[str]:
    """
    Normalize a date-bound parameter coming from the API to a clean
    YYYY-MM-DD string suitable for string comparison against the
    pre-truncated `n.date` property.

    The API historically accepts:
      - "2024-03-15"                         (already correct)
      - "2024-03-15T14:23:11.000Z"           (ISO with T)
      - "2024-03-15 14:23:11+02:00"          (ISO with space)
      - "2024-03-15T14:23:11"                (naive ISO)

    Returns None for anything we can't confidently parse, so the caller
    can drop the filter rather than apply a broken predicate. The previous
    code passed the raw value into a Cypher string comparison against
    `n.timestamp`, which silently produced wrong results when the stored
    timestamp had a different format than the bound (the user-reported
    "2022 data appearing in newer windows" bug).
    """
    if value is None:
        return None
    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception:
            return None
    s = value.strip()
    if not s:
        return None
    # Cut at first 'T' or whitespace - both are valid ISO separators.
    for sep in ("T", " "):
        if sep in s:
            s = s.split(sep, 1)[0]
            break
    # Strip timezone designators that snuck through (rare).
    if s.endswith("Z"):
        s = s[:-1]
    # Validate YYYY-MM-DD shape without pulling datetime in the hot path.
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return None
    try:
        int(s[0:4]); int(s[5:7]); int(s[8:10])
    except ValueError:
        return None
    return s


def _decode_reconciliation(value: Optional[str]) -> Optional[dict]:
    """
    Decode the JSON-stringified reconciliation report stored on PhoneReport
    nodes by the ingestion pipeline. Returns None if missing or malformed,
    so the API just omits the field for older reports.
    """
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


class CellebriteNeo4jService:
    """Neo4j-backed Cellebrite report, comms, event, and overview queries."""

    def __init__(self):
        self._driver = driver
        self._ensure_cellebrite_indexes()

    def _ensure_cellebrite_indexes(self):
        """
        Composite range indexes on (case_id, cellebrite_report_key) for the
        labels every Cellebrite tab filters on. Without these, queries like
        `MATCH (c:Communication {case_id, cellebrite_report_key, source_type})`
        do a full label scan + property filter on every load - turning Comms
        Center / Timeline / Location & Events into multi-second waits even
        for cases with only a few thousand records.

        Index creation is online (writes are not blocked) and IF NOT EXISTS
        means subsequent boots are no-ops.
        """
        composite_labels = [
            "Person", "PhoneCall", "Communication", "Email", "Location",
            "CellTower", "WirelessNetwork", "DeviceEvent", "AppSession",
            "SearchedItem", "VisitedPage", "Meeting",
        ]
        single_indexes = [
            ("PhoneReport", "key"),
            ("Communication", "chat_id"),
            ("Communication", "timestamp"),
            ("PhoneCall", "timestamp"),
            ("Email", "timestamp"),
            ("Location", "timestamp"),
        ]
        try:
            with self._driver.session() as session:
                for label in composite_labels:
                    idx_name = f"idx_{label.lower()}_case_report"
                    session.run(
                        f"CREATE INDEX {idx_name} IF NOT EXISTS "
                        f"FOR (n:{label}) ON (n.case_id, n.cellebrite_report_key)"
                    )
                for label, prop in single_indexes:
                    idx_name = f"idx_{label.lower()}_{prop}"
                    session.run(
                        f"CREATE INDEX {idx_name} IF NOT EXISTS "
                        f"FOR (n:{label}) ON (n.{prop})"
                    )
        except Exception:
            # Stay resilient on boot - slow queries are better than a crashed backend.
            pass

    def get_cellebrite_reports(self, case_id: str) -> list:
        """Get all PhoneReport nodes for a case with owner info and stats."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (r:PhoneReport {case_id: $case_id})
                OPTIONAL MATCH (r)-[:BELONGS_TO]->(owner:Person)

                // Count related nodes by label
                OPTIONAL MATCH (contact:Person {case_id: $case_id, cellebrite_report_key: r.key})
                  WHERE contact.source_type = 'cellebrite'
                    AND contact <> owner
                WITH r, owner, count(DISTINCT contact) AS contact_count

                OPTIONAL MATCH (call:PhoneCall {case_id: $case_id, cellebrite_report_key: r.key})
                WITH r, owner, contact_count, count(DISTINCT call) AS call_count

                OPTIONAL MATCH (msg:Communication {case_id: $case_id, cellebrite_report_key: r.key})
                WITH r, owner, contact_count, call_count, count(DISTINCT msg) AS message_count

                OPTIONAL MATCH (loc:Location {case_id: $case_id, cellebrite_report_key: r.key})
                WITH r, owner, contact_count, call_count, message_count, count(DISTINCT loc) AS location_count

                OPTIONAL MATCH (email:Email {case_id: $case_id, cellebrite_report_key: r.key})
                WITH r, owner, contact_count, call_count, message_count, location_count, count(DISTINCT email) AS email_count

                RETURN r, owner,
                       contact_count, call_count, message_count, location_count, email_count
                ORDER BY coalesce(r.evidence_number, ''),
                         coalesce(r.case_number, ''),
                         coalesce(r.key, '')
                """,
                case_id=case_id,
            )

            reports = []
            for idx, record in enumerate(result):
                r = dict(record["r"])
                owner = dict(record["owner"]) if record["owner"] else None

                # Effective device name precedence:
                #   1. investigator-supplied override
                #   2. parser-detected manufacturer + device_model
                #   3. parser-detected device_model alone
                #   4. literal fallback
                manufacturer = r.get("manufacturer") or ""
                detected_model = r.get("device_model") or ""
                override = r.get("device_name_override") or ""
                if override:
                    effective = override
                elif manufacturer and detected_model:
                    effective = f"{manufacturer} {detected_model}"
                elif detected_model:
                    effective = detected_model
                else:
                    effective = "Unknown Device"

                # Detected name candidates were JSON-encoded by the writer
                # because Neo4j can't store list-of-maps natively.
                import json as _json
                candidates_raw = r.get("device_name_candidates")
                candidates: list = []
                if candidates_raw:
                    try:
                        parsed = _json.loads(candidates_raw)
                        if isinstance(parsed, list):
                            candidates = parsed
                    except (ValueError, TypeError):
                        candidates = []

                # Defensive dedupe: the writer creates PhoneReport with raw
                # CREATE (no uniqueness constraint), so a re-ingest of the
                # same report can leave a stale duplicate node in the graph.
                # Skip rows whose key was already emitted - both copies carry
                # identical data, so the second is redundant.
                report_key = r.get("key", "")
                if report_key and any(
                    existing["report_key"] == report_key for existing in reports
                ):
                    continue

                reports.append({
                    "report_key": report_key,
                    "report_name": r.get("name", ""),
                    # Stable zero-based palette slot for the frontend phone
                    # identity. Ordering above guarantees the same phone gets
                    # the same colour across calls, refreshes and users.
                    "display_index": idx,
                    # `device_model` is the *effective* display name so
                    # every existing UI surface picks up the new
                    # manufacturer composition + override automatically.
                    "device_model": effective,
                    "manufacturer": manufacturer,
                    "detected_device_model": detected_model,
                    "device_name_override": override or None,
                    "device_name_candidates": candidates,
                    "accessory_imeis": list(r.get("accessory_imeis") or []),
                    "phone_numbers": r.get("phone_numbers", ""),
                    "imei": r.get("imei", ""),
                    "extraction_type": r.get("extraction_type", ""),
                    "extraction_date": r.get("extraction_start", ""),
                    "examiner": r.get("examiner", ""),
                    "case_number": r.get("case_number", ""),
                    "evidence_number": r.get("evidence_number", ""),
                    "phone_owner_name": owner.get("name", "") if owner else "",
                    "phone_owner_key": owner.get("key", "") if owner else "",
                    "stats": {
                        "contacts": record["contact_count"],
                        "calls": record["call_count"],
                        "messages": record["message_count"],
                        "locations": record["location_count"],
                        "emails": record["email_count"],
                    },
                    # Per-modelType reconciliation (XML count vs persisted
                    # count). Stored as JSON on the PhoneReport node by the
                    # ingestion pipeline; absent for reports ingested before
                    # the reconciliation feature shipped.
                    "reconciliation": _decode_reconciliation(
                        r.get("ingest_reconciliation")
                    ),
                })
            return reports

    def find_existing_phone_report(
        self,
        case_id: str,
        report_key: Optional[str] = None,
        imei: Optional[str] = None,
        evidence_number: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Look up an already-ingested PhoneReport in the case that would
        collide with a new ingest.

        A "collision" is any of:
          - same report_key (case_number + evidence_number tuple)
          - same non-empty IMEI
          - same evidence_number with same case_number

        Returns the existing report's summary dict, or None.
        """
        # Build the WHERE clause dynamically so we don't accidentally
        # match every record in the case when callers pass blank values.
        clauses = []
        params: dict = {"case_id": case_id}

        if report_key:
            clauses.append("r.key = $report_key")
            params["report_key"] = report_key
        if imei:
            clauses.append("(r.imei IS NOT NULL AND r.imei <> '' AND r.imei = $imei)")
            params["imei"] = imei
        if evidence_number:
            clauses.append(
                "(r.evidence_number IS NOT NULL AND r.evidence_number <> '' "
                "AND r.evidence_number = $evidence_number)"
            )
            params["evidence_number"] = evidence_number

        if not clauses:
            return None

        query = (
            "MATCH (r:PhoneReport {case_id: $case_id}) "
            "WHERE " + " OR ".join(clauses) + " "
            "OPTIONAL MATCH (r)-[:BELONGS_TO]->(owner:Person) "
            "RETURN r, owner LIMIT 1"
        )

        with self._driver.session() as session:
            result = session.run(query, **params)
            record = result.single()
            if not record:
                return None
            r = dict(record["r"])
            owner = dict(record["owner"]) if record["owner"] else None
            manufacturer = r.get("manufacturer") or ""
            detected_model = r.get("device_model") or ""
            override = r.get("device_name_override") or ""
            if override:
                effective = override
            elif manufacturer and detected_model:
                effective = f"{manufacturer} {detected_model}"
            elif detected_model:
                effective = detected_model
            else:
                effective = "Unknown Device"
            return {
                "report_key": r.get("key", ""),
                "report_name": r.get("name", ""),
                "device_model": effective,
                "case_number": r.get("case_number", ""),
                "evidence_number": r.get("evidence_number", ""),
                "imei": r.get("imei", ""),
                "phone_owner_name": owner.get("name", "") if owner else "",
            }

    def delete_phone_report(self, case_id: str, report_key: str) -> dict:
        """
        Delete a PhoneReport node and every node tagged with the same
        cellebrite_report_key in the case.

        Returns counts so callers can confirm what was removed.
        """
        with self._driver.session() as session:
            # Count first so we can report what got deleted. Counting
            # before delete also confirms the report exists.
            count_result = session.run(
                """
                MATCH (n {case_id: $case_id, cellebrite_report_key: $key})
                RETURN count(n) AS tagged_node_count
                """,
                case_id=case_id,
                key=report_key,
            )
            tagged = count_result.single()["tagged_node_count"] if count_result else 0

            report_count_result = session.run(
                "MATCH (r:PhoneReport {case_id: $case_id, key: $key}) RETURN count(r) AS c",
                case_id=case_id,
                key=report_key,
            )
            report_count = report_count_result.single()["c"] if report_count_result else 0

            if report_count == 0 and tagged == 0:
                return {
                    "status": "not_found",
                    "report_key": report_key,
                    "deleted_nodes": 0,
                    "deleted_phone_report": 0,
                }

            # Delete every node carrying this report key (relationships
            # are removed automatically with DETACH DELETE).
            session.run(
                """
                MATCH (n {case_id: $case_id, cellebrite_report_key: $key})
                DETACH DELETE n
                """,
                case_id=case_id,
                key=report_key,
            )
            # And the central PhoneReport node itself (it carries `key`,
            # not `cellebrite_report_key`, so it won't have matched above).
            session.run(
                """
                MATCH (r:PhoneReport {case_id: $case_id, key: $key})
                DETACH DELETE r
                """,
                case_id=case_id,
                key=report_key,
            )

            return {
                "status": "deleted",
                "report_key": report_key,
                "deleted_nodes": tagged,
                "deleted_phone_report": report_count,
            }

    def update_phone_report_name_override(
        self,
        case_id: str,
        report_key: str,
        device_name_override: Optional[str],
    ) -> Optional[dict]:
        """
        Set or clear the investigator-supplied device-name override on a
        PhoneReport. Pass None or empty string to clear.

        Returns the updated report summary, or None when the report
        does not exist in the case.
        """
        cleaned = (device_name_override or "").strip() or None
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (r:PhoneReport {case_id: $case_id, key: $key})
                SET r.device_name_override = $override
                RETURN r
                """,
                case_id=case_id,
                key=report_key,
                override=cleaned,
            )
            record = result.single()
            if not record:
                return None
            r = dict(record["r"])
            return {
                "report_key": r.get("key", ""),
                "device_name_override": r.get("device_name_override") or None,
                "manufacturer": r.get("manufacturer") or "",
                "detected_device_model": r.get("device_model") or "",
            }

    def get_cellebrite_cross_phone_graph(self, case_id: str) -> dict:
        """
        Get cross-phone graph showing shared entities across devices.

        Returns nodes and links in react-force-graph-2d format.
        """
        nodes = []
        links = []
        seen_nodes = set()

        with self._driver.session() as session:
            # 1. Get PhoneReport nodes
            result = session.run(
                """
                MATCH (r:PhoneReport {case_id: $case_id})
                OPTIONAL MATCH (r)-[:BELONGS_TO]->(owner:Person)
                RETURN r, owner
                """,
                case_id=case_id,
            )
            report_keys = []
            for record in result:
                r = dict(record["r"])
                rkey = r.get("key", "")
                report_keys.append(rkey)
                node_id = f"report-{rkey}"
                if node_id not in seen_nodes:
                    seen_nodes.add(node_id)
                    owner = dict(record["owner"]) if record["owner"] else None
                    nodes.append({
                        "id": node_id,
                        "name": r.get("device_model", "Unknown Device"),
                        "type": "PhoneReport",
                        "report_key": rkey,
                        "phone_owner": owner.get("name", "") if owner else "",
                        "val": 8,
                    })
                    # Link report to its owner
                    if owner:
                        owner_id = f"person-{owner.get('key', '')}"
                        links.append({
                            "source": node_id,
                            "target": owner_id,
                            "label": "BELONGS_TO",
                        })

            if len(report_keys) < 1:
                return {"nodes": nodes, "links": links}

            # 2. Find persons connected to PhoneReport nodes via relationships
            result = session.run(
                """
                MATCH (r:PhoneReport {case_id: $case_id})
                MATCH (p:Person {case_id: $case_id, source_type: 'cellebrite'})
                WHERE p.cellebrite_report_key = r.key
                WITH p, collect(DISTINCT r.key) AS device_keys,
                     count(DISTINCT r) AS device_count
                // Get communication counts
                OPTIONAL MATCH (p)-[rel]->()
                WHERE type(rel) IN ['CALLED', 'SENT_MESSAGE', 'EMAILED', 'PARTICIPATED_IN']
                WITH p, device_keys, device_count, count(rel) AS comm_count
                ORDER BY device_count DESC, comm_count DESC
                LIMIT 200
                RETURN p, device_keys, device_count, comm_count
                """,
                case_id=case_id,
            )

            for record in result:
                p = dict(record["p"])
                pkey = p.get("key", "")
                node_id = f"person-{pkey}"
                device_keys = list(record["device_keys"])
                device_count = record["device_count"]

                if node_id not in seen_nodes:
                    seen_nodes.add(node_id)
                    nodes.append({
                        "id": node_id,
                        "name": p.get("name", pkey),
                        "type": "Person",
                        "phone": p.get("phone", ""),
                        "device_count": device_count,
                        "shared": device_count > 1,
                        "comm_count": record["comm_count"],
                        "val": 3 + min(record["comm_count"], 10),
                    })

                # Link person to each device's report
                for dk in device_keys:
                    report_node_id = f"report-{dk}"
                    if report_node_id in seen_nodes:
                        links.append({
                            "source": report_node_id,
                            "target": node_id,
                            "label": "CONTAINS_CONTACT",
                        })

            # 3. Find direct communication links between persons
            result = session.run(
                """
                MATCH (a:Person {case_id: $case_id, source_type: 'cellebrite'})
                      -[rel]->(comm)
                      -[rel2]->(b:Person {case_id: $case_id})
                WHERE type(rel) IN ['CALLED', 'SENT_MESSAGE', 'EMAILED']
                  AND type(rel2) IN ['CALLED_TO', 'SENT_TO']
                  AND a <> b
                WITH a.key AS src, b.key AS tgt, type(rel) AS rel_type, count(*) AS cnt
                WHERE cnt >= 2
                RETURN src, tgt, rel_type, cnt
                ORDER BY cnt DESC
                LIMIT 300
                """,
                case_id=case_id,
            )

            for record in result:
                src_id = f"person-{record['src']}"
                tgt_id = f"person-{record['tgt']}"
                if src_id in seen_nodes and tgt_id in seen_nodes:
                    links.append({
                        "source": src_id,
                        "target": tgt_id,
                        "label": record["rel_type"],
                        "count": record["cnt"],
                    })

        return {"nodes": nodes, "links": links}

    def get_cellebrite_timeline(
        self,
        case_id: str,
        report_keys: list = None,
        start_date: str = None,
        end_date: str = None,
        event_types: list = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict:
        """Get chronological events across all phone reports."""
        # Build WHERE clause fragments
        where_parts = ["n.case_id = $case_id"]
        params = {"case_id": case_id, "limit": limit, "skip_count": offset}

        if report_keys:
            where_parts.append("n.cellebrite_report_key IN $report_keys")
            params["report_keys"] = report_keys

        sd = _normalize_date_bound(start_date)
        ed = _normalize_date_bound(end_date)
        if sd:
            where_parts.append("coalesce(n.date, n.timestamp, '') >= $start_date")
            params["start_date"] = sd

        if ed:
            where_parts.append("coalesce(n.date, n.timestamp, '') <= $end_date")
            params["end_date"] = ed

        where_clause = " AND ".join(where_parts)

        # Build UNION query across event types
        union_parts = []
        type_map = {
            "call": ("PhoneCall", "phone_number_to", "CALLED"),
            "message": ("Communication", "body", "SENT_MESSAGE"),
            "location": ("Location", "name", "WAS_AT"),
            "email": ("Email", "subject", "EMAILED"),
        }

        active_types = event_types if event_types else list(type_map.keys())

        # Per-type cap = offset + limit. The first (offset+limit) globally
        # ordered rows are guaranteed to come from the per-type top
        # (offset+limit) by the same order - so capping inside each UNION
        # subquery preserves correctness while bounding the scan to
        # `len(active_types) x per_type_cap` rows instead of "every matching
        # row in the case".
        per_type_cap = max(limit + offset, limit)
        params["per_type_cap"] = per_type_cap

        for etype in active_types:
            if etype not in type_map:
                continue
            label, summary_field, _ = type_map[etype]
            union_parts.append(f"""
                MATCH (n:{label})
                WHERE {where_clause}
                  AND n.timestamp IS NOT NULL
                  AND n.source_type = 'cellebrite'
                WITH n.timestamp AS timestamp,
                     '{etype}' AS event_type,
                     coalesce(n.{summary_field}, '') AS summary,
                     n.cellebrite_report_key AS report_key,
                     n.key AS node_key
                ORDER BY timestamp
                LIMIT $per_type_cap
                RETURN timestamp, event_type, summary, report_key, node_key
            """)

        if not union_parts:
            return {"events": [], "total_estimate": 0}

        query = " UNION ALL ".join(union_parts)
        query += """
            ORDER BY timestamp
            SKIP $skip_count
            LIMIT $limit
        """

        with self._driver.session() as session:
            result = session.run(query, params)
            events = []
            for record in result:
                events.append({
                    "timestamp": record["timestamp"],
                    "event_type": record["event_type"],
                    "summary": record["summary"],
                    "report_key": record["report_key"],
                    "node_key": record["node_key"],
                })

        return {"events": events, "total_estimate": len(events)}

    def get_cellebrite_communication_network(self, case_id: str) -> dict:
        """Get contact frequency analysis and shared contacts across devices."""
        with self._driver.session() as session:
            # Get all persons with communication counts per report
            result = session.run(
                """
                MATCH (p:Person {case_id: $case_id, source_type: 'cellebrite'})
                OPTIONAL MATCH (p)-[:CALLED]->(call:PhoneCall {case_id: $case_id})
                WITH p, count(DISTINCT call) AS calls_made
                OPTIONAL MATCH ()-[:CALLED]->(call2:PhoneCall {case_id: $case_id})-[:CALLED_TO]->(p)
                WITH p, calls_made, count(DISTINCT call2) AS calls_received
                OPTIONAL MATCH (p)-[:SENT_MESSAGE]->(msg:Communication {case_id: $case_id})
                WITH p, calls_made, calls_received, count(DISTINCT msg) AS messages_sent
                OPTIONAL MATCH (p)-[:EMAILED]->(e:Email {case_id: $case_id})
                WITH p, calls_made, calls_received, messages_sent, count(DISTINCT e) AS emails_sent

                // Find which devices this person appears on
                WITH p, calls_made, calls_received, messages_sent, emails_sent,
                     CASE WHEN p.cellebrite_report_key IS NOT NULL
                          THEN [p.cellebrite_report_key]
                          ELSE [] END AS device_keys

                WHERE calls_made + calls_received + messages_sent + emails_sent > 0

                RETURN p.key AS person_key,
                       p.name AS name,
                       p.phone AS phone,
                       calls_made + calls_received AS call_count,
                       messages_sent AS message_count,
                       emails_sent AS email_count,
                       device_keys
                ORDER BY calls_made + calls_received + messages_sent + emails_sent DESC
                LIMIT 500
                """,
                case_id=case_id,
            )

            contacts = []
            shared_contacts = []
            for record in result:
                contact = {
                    "person_key": record["person_key"],
                    "name": record["name"] or record["person_key"],
                    "phone": record["phone"] or "",
                    "call_count": record["call_count"],
                    "message_count": record["message_count"],
                    "email_count": record["email_count"],
                    "devices": list(record["device_keys"]),
                }
                contacts.append(contact)

            # Find contacts appearing on multiple devices
            result = session.run(
                """
                MATCH (p:Person {case_id: $case_id, source_type: 'cellebrite'})
                WITH p, p.cellebrite_report_key AS rk
                WHERE rk IS NOT NULL
                WITH p.key AS person_key, p.name AS name, p.phone AS phone,
                     collect(DISTINCT rk) AS device_keys
                WHERE size(device_keys) > 1
                RETURN person_key, name, phone, device_keys
                ORDER BY size(device_keys) DESC, name
                """,
                case_id=case_id,
            )

            for record in result:
                shared_contacts.append({
                    "person_key": record["person_key"],
                    "name": record["name"] or record["person_key"],
                    "phone": record["phone"] or "",
                    "devices": list(record["device_keys"]),
                })

        return {"contacts": contacts, "shared_contacts": shared_contacts}

    def get_cellebrite_comms_entities(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
        with_counts: bool = False,
    ) -> list:
        """
        Get all distinct Person entities for the Comms Center filter panels.

        Deduplicated by Person.key across devices.

        with_counts: when True, returns the original behaviour - five
            extra OPTIONAL MATCH + collect(DISTINCT id) aggregations
            per entity to compute call/message/email counts. Slow on
            big cases (OPDMD28: 12s, 13 MB for 13K entities).

            When False (default), returns only the cheap fields the
            filter UI actually needs to render - name, phone_numbers,
            is_owner, device_keys, device_count. Frontend sort by
            comms-volume degrades to sort-by-name; it can re-fetch
            with with_counts=true on demand if the user picks an
            activity-based sort.
        """
        params: Dict[str, Any] = {"case_id": case_id}
        report_filter = ""
        if report_keys:
            report_filter = "AND p.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        with self._driver.session() as session:
            if with_counts:
                # Slow path - preserved for callers that explicitly opt in.
                query = f"""
                    MATCH (p:Person {{case_id: $case_id, source_type: 'cellebrite'}})
                    WHERE p.key IS NOT NULL {report_filter}
                    WITH p.key AS key,
                         collect(DISTINCT p) AS persons,
                         collect(DISTINCT p.cellebrite_report_key) AS device_keys,
                         collect(DISTINCT p.name) AS names,
                         collect(DISTINCT p.phone_numbers) AS phone_lists,
                         max(toString(coalesce(p.is_phone_owner, false))) AS is_owner_str

                    // Count comms involving any of these person-instances
                    UNWIND persons AS person
                    OPTIONAL MATCH (person)-[:CALLED]->(c:PhoneCall)
                      WHERE (size($report_keys_list) = 0 OR c.cellebrite_report_key IN $report_keys_list)
                    WITH key, device_keys, names, phone_lists, is_owner_str, persons,
                         collect(DISTINCT c.id) AS calls_out_ids

                    UNWIND persons AS person
                    OPTIONAL MATCH (c2:PhoneCall)-[:CALLED_TO]->(person)
                      WHERE (size($report_keys_list) = 0 OR c2.cellebrite_report_key IN $report_keys_list)
                    WITH key, device_keys, names, phone_lists, is_owner_str, persons,
                         calls_out_ids, collect(DISTINCT c2.id) AS calls_in_ids

                    UNWIND persons AS person
                    OPTIONAL MATCH (person)-[:SENT_MESSAGE]->(m:Communication)
                      WHERE m.body IS NOT NULL
                        AND (size($report_keys_list) = 0 OR m.cellebrite_report_key IN $report_keys_list)
                    WITH key, device_keys, names, phone_lists, is_owner_str,
                         calls_out_ids, calls_in_ids, persons,
                         collect(DISTINCT m.id) AS msgs_sent_ids

                    UNWIND persons AS person
                    OPTIONAL MATCH (person)-[:PARTICIPATED_IN]->(chat:Communication)
                      WHERE chat.chat_id IS NOT NULL
                        AND (size($report_keys_list) = 0 OR chat.cellebrite_report_key IN $report_keys_list)
                    OPTIONAL MATCH (msg:Communication)-[:PART_OF]->(chat)
                      WHERE msg.body IS NOT NULL
                    WITH key, device_keys, names, phone_lists, is_owner_str,
                         calls_out_ids, calls_in_ids, msgs_sent_ids, persons,
                         collect(DISTINCT msg.id) AS msgs_received_ids

                    UNWIND persons AS person
                    OPTIONAL MATCH (person)-[:EMAILED]->(e1:Email)
                      WHERE (size($report_keys_list) = 0 OR e1.cellebrite_report_key IN $report_keys_list)
                    WITH key, device_keys, names, phone_lists, is_owner_str,
                         calls_out_ids, calls_in_ids, msgs_sent_ids, msgs_received_ids, persons,
                         collect(DISTINCT e1.id) AS emails_sent_ids

                    UNWIND persons AS person
                    OPTIONAL MATCH (e2:Email)-[:SENT_TO]->(person)
                      WHERE (size($report_keys_list) = 0 OR e2.cellebrite_report_key IN $report_keys_list)
                    WITH key, device_keys, names, phone_lists, is_owner_str,
                         calls_out_ids, calls_in_ids, msgs_sent_ids, msgs_received_ids,
                         emails_sent_ids, collect(DISTINCT e2.id) AS emails_received_ids

                    RETURN key,
                           head(names) AS name,
                           head(phone_lists) AS phone_numbers,
                           is_owner_str = 'true' AS is_owner,
                           device_keys,
                           size(device_keys) AS device_count,
                           size(calls_out_ids) + size(calls_in_ids) AS call_count,
                           size(msgs_sent_ids) + size(msgs_received_ids) AS message_count,
                           size(emails_sent_ids) + size(emails_received_ids) AS email_count,
                           size(calls_out_ids) + size(msgs_sent_ids) + size(emails_sent_ids) AS as_sender_count,
                           size(calls_in_ids) + size(msgs_received_ids) + size(emails_received_ids) AS as_recipient_count
                    ORDER BY call_count + message_count + email_count DESC
                """
                params["report_keys_list"] = list(report_keys) if report_keys else []
                result = session.run(query, params)
                entities = []
                for record in result:
                    entities.append({
                        "key": record["key"],
                        "name": record["name"] or record["key"],
                        "phone_numbers": record["phone_numbers"] or [],
                        "is_owner": bool(record["is_owner"]),
                        "device_keys": list(record["device_keys"] or []),
                        "device_count": int(record["device_count"] or 0),
                        "call_count": int(record["call_count"] or 0),
                        "message_count": int(record["message_count"] or 0),
                        "email_count": int(record["email_count"] or 0),
                        "as_sender_count": int(record["as_sender_count"] or 0),
                        "as_recipient_count": int(record["as_recipient_count"] or 0),
                    })
                return entities

            # Lean path - what the entity-filter UI actually needs to
            # render. No interaction-count aggregations; sorts default
            # to alphabetical until the caller opts in to with_counts.
            # Empirically ~80% smaller payload + ~80% faster Cypher on
            # OPDMD28 (13s/13MB -> ~2s/2MB). Frontend filter still works
            # for picking participants; it just can't sort by activity
            # until counts are populated.
            query = f"""
                MATCH (p:Person {{case_id: $case_id, source_type: 'cellebrite'}})
                WHERE p.key IS NOT NULL {report_filter}
                WITH p.key AS key,
                     collect(DISTINCT p.cellebrite_report_key) AS device_keys,
                     collect(DISTINCT p.name) AS names,
                     collect(DISTINCT p.phone_numbers) AS phone_lists,
                     max(toString(coalesce(p.is_phone_owner, false))) AS is_owner_str
                RETURN key,
                       head(names) AS name,
                       head(phone_lists) AS phone_numbers,
                       is_owner_str = 'true' AS is_owner,
                       device_keys,
                       size(device_keys) AS device_count
                ORDER BY name
            """
            result = session.run(query, params)
            entities = []
            for record in result:
                entities.append({
                    "key": record["key"],
                    "name": record["name"] or record["key"],
                    "phone_numbers": record["phone_numbers"] or [],
                    "is_owner": bool(record["is_owner"]),
                    "device_keys": list(record["device_keys"] or []),
                    "device_count": int(record["device_count"] or 0),
                    # Count keys are intentionally OMITTED from lean
                    # responses - re-fetch with with_counts=true to get
                    # them. Frontend reads use the (e.call_count || 0)
                    # idiom so missing keys are safe; previously we
                    # zeroed-and-shipped these and that turned out to
                    # be ~6 MB of pointless transit on a 13K-entity
                    # case (per on-box perf measurement).
                })
            return entities

    def get_cellebrite_comms_source_apps(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
    ) -> list:
        """
        Get distinct source_app values (e.g. WhatsApp, Facebook Messenger, SMS, Gmail)
        that exist in the current (optionally report-filtered) universe, with counts.

        Returns: [{source_app, thread_type, count}, ...]  - thread_type is
        'chat' for messages, 'calls' for PhoneCall, 'emails' for Email.
        """
        params: Dict[str, Any] = {"case_id": case_id}
        rk_filter = ""
        if report_keys:
            rk_filter = "AND n.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        apps: list = []
        with self._driver.session() as session:
            # Messages / chats (Communication with body or chat_id)
            r = session.run(
                f"""
                MATCH (n:Communication {{case_id: $case_id, source_type: 'cellebrite'}})
                WHERE n.source_app IS NOT NULL
                  AND (n.body IS NOT NULL OR n.chat_id IS NOT NULL)
                  {rk_filter}
                RETURN n.source_app AS app, count(n) AS n
                ORDER BY n DESC
                """,
                params,
            )
            for rec in r:
                apps.append({"source_app": rec["app"], "thread_type": "chat", "count": int(rec["n"])})

            r = session.run(
                f"""
                MATCH (n:PhoneCall {{case_id: $case_id, source_type: 'cellebrite'}})
                WHERE n.source_app IS NOT NULL {rk_filter}
                RETURN n.source_app AS app, count(n) AS n
                ORDER BY n DESC
                """,
                params,
            )
            for rec in r:
                apps.append({"source_app": rec["app"], "thread_type": "calls", "count": int(rec["n"])})

            r = session.run(
                f"""
                MATCH (n:Email {{case_id: $case_id, source_type: 'cellebrite'}})
                WHERE n.source_app IS NOT NULL {rk_filter}
                RETURN n.source_app AS app, count(n) AS n
                ORDER BY n DESC
                """,
                params,
            )
            for rec in r:
                apps.append({"source_app": rec["app"], "thread_type": "emails", "count": int(rec["n"])})

        return apps

    def get_cellebrite_comms_threads(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
        participant_keys: Optional[List[str]] = None,
        from_keys: Optional[List[str]] = None,
        to_keys: Optional[List[str]] = None,
        thread_types: Optional[List[str]] = None,
        source_apps: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list:
        """
        Get conversation threads - real chat threads + synthetic call/email threads per participant pair.

        thread_types controls which kinds to include: 'chat', 'calls', 'emails'.
        When from_keys/to_keys are provided, returns only threads involving those pairs.
        """
        active_types = set(thread_types) if thread_types else {"chat", "calls", "emails"}
        threads: list = []

        # Per-block cap. Each thread block (chat / calls / emails) returns at
        # most this many threads before the final merge / sort / paginate. The
        # cap exists primarily to bound the *expansion* work on large cases
        # (e.g. don't OPTIONAL MATCH every message in every chat just to
        # compute counts that the user won't scroll to). Truncation is
        # surfaced to the caller via `truncated`.
        per_block_cap = max(limit + offset, limit)
        truncated = False

        rk_filter_chat = ""
        rk_filter_call = ""
        rk_filter_email = ""
        params: Dict[str, Any] = {"case_id": case_id, "per_block_cap": per_block_cap}
        if report_keys:
            rk_filter_chat = "AND chat.cellebrite_report_key IN $report_keys"
            rk_filter_call = "AND c.cellebrite_report_key IN $report_keys"
            rk_filter_email = "AND e.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        # Source-app filter (e.g. only WhatsApp + Facebook Messenger). Empty / None = all.
        app_filter_chat = ""
        app_filter_call = ""
        app_filter_email = ""
        if source_apps:
            app_filter_chat = "AND chat.source_app IN $source_apps"
            app_filter_call = "AND c.source_app IN $source_apps"
            app_filter_email = "AND e.source_app IN $source_apps"
            params["source_apps"] = list(source_apps)

        # Normalize date bounds to YYYY-MM-DD up front. Compare against the
        # pre-truncated `n.date` property where available (always populated
        # by the Cellebrite writer for events with a timestamp); for chat
        # threads - which carry `last_activity`/`start_time` strings only -
        # use a substring prefix that's still safe across timezone formats.
        date_filter_chat = ""
        date_filter_call = ""
        date_filter_email = ""
        sd = _normalize_date_bound(start_date)
        ed = _normalize_date_bound(end_date)
        if sd:
            # PhoneCall / Email have a real `date` column; chats only have
            # `last_activity` as an ISO string - prefix-compare is correct
            # because YYYY-MM-DD orders the same lexicographically as ISO.
            date_filter_chat += " AND coalesce(chat.last_activity, '') >= $start_date"
            date_filter_call += " AND coalesce(c.date, c.timestamp, '') >= $start_date"
            date_filter_email += " AND coalesce(e.date, e.timestamp, '') >= $start_date"
            params["start_date"] = sd
        if ed:
            # Use end-of-day inclusive bound so a YYYY-MM-DD upper limit
            # actually includes events from that day. Without this, an
            # end_date='2024-03-15' would exclude any event on 2024-03-15.
            ed_inclusive = f"{ed}T23:59:59.999"
            date_filter_chat += " AND coalesce(chat.start_time, chat.last_activity, '') <= $end_date_incl"
            date_filter_call += " AND coalesce(c.date, c.timestamp, '') <= $end_date"
            date_filter_email += " AND coalesce(e.date, e.timestamp, '') <= $end_date"
            params["end_date"] = ed
            params["end_date_incl"] = ed_inclusive

        with self._driver.session() as session:
            # ---- Chat threads (real Communication nodes with chat_id) ----
            if "chat" in active_types:
                search_clause = ""
                if search:
                    search_clause = " AND (toLower(chat.name) CONTAINS toLower($search) OR toLower(chat.source_app) CONTAINS toLower($search))"
                    params["search"] = search

                # Pre-cap chats using the denormalized chat.last_activity
                # property *before* the per-chat OPTIONAL MATCH on messages
                # - without this, every chat in the case has its messages
                # expanded just to compute counts. For a case with thousands
                # of chats this was the dominant cost in Comms Center load.
                query = f"""
                    MATCH (chat:Communication {{case_id: $case_id, source_type: 'cellebrite'}})
                    WHERE chat.chat_id IS NOT NULL {rk_filter_chat} {app_filter_chat} {date_filter_chat} {search_clause}
                    WITH chat
                    ORDER BY chat.last_activity IS NULL, chat.last_activity DESC
                    LIMIT $per_block_cap
                    OPTIONAL MATCH (p:Person)-[:PARTICIPATED_IN]->(chat)
                    OPTIONAL MATCH (msg:Communication)-[:PART_OF]->(chat)
                      WHERE msg.body IS NOT NULL
                    WITH chat, collect(DISTINCT p) AS participants,
                         count(DISTINCT msg) AS msg_count,
                         sum(coalesce(msg.attachment_count, 0)) AS attach_count,
                         max(msg.timestamp) AS last_msg_ts,
                         min(msg.timestamp) AS first_msg_ts
                    RETURN chat, participants, msg_count, attach_count, last_msg_ts, first_msg_ts
                    ORDER BY coalesce(last_msg_ts, chat.last_activity) DESC
                """
                chat_block_count = 0
                result = session.run(query, params)
                for record in result:
                    chat_block_count += 1
                    chat = dict(record["chat"])
                    participants = [dict(p) for p in record["participants"] if p is not None]

                    # Participant filter: if from_keys or to_keys provided, ensure at least one matches.
                    # `participant_keys` is the involvement (OR) variant - used by Filter Comms
                    # intents and the "Any direction" mode of the Participants picker. A thread
                    # passes when at least one of its participants is in the involvement set
                    # (sender OR receiver - direction-agnostic). Layered on top of the existing
                    # from/to AND filters so callers can mix all three.
                    if from_keys or to_keys or participant_keys:
                        pkeys = {p.get("key") for p in participants if p.get("key")}
                        if from_keys and not any(k in pkeys for k in from_keys):
                            continue
                        if to_keys and not any(k in pkeys for k in to_keys):
                            continue
                        if participant_keys and not any(k in pkeys for k in participant_keys):
                            continue

                    threads.append({
                        "thread_id": chat.get("key"),
                        "thread_type": "chat",
                        "source_app": chat.get("source_app") or "",
                        "name": chat.get("name") or "Chat",
                        "participants": [
                            {
                                "key": p.get("key"),
                                "name": p.get("name") or p.get("key"),
                                "is_owner": bool(p.get("is_phone_owner")),
                            }
                            for p in participants
                        ],
                        "message_count": int(record["msg_count"] or chat.get("message_count") or 0),
                        "attachment_count": int(record["attach_count"] or 0),
                        "has_attachments": int(record["attach_count"] or 0) > 0,
                        "last_activity": record["last_msg_ts"] or chat.get("last_activity"),
                        "first_activity": record["first_msg_ts"] or chat.get("start_time"),
                        "report_key": chat.get("cellebrite_report_key"),
                    })
                if chat_block_count >= per_block_cap:
                    truncated = True

            # ---- Synthetic call threads (per participant pair + report) ----
            if "calls" in active_types:
                # Cap pair aggregations after the WITH so we don't materialise
                # one row per (caller, callee, report) for cases with millions
                # of permutations. ORDER BY call_count DESC keeps the
                # most-active pairs which are the likely-of-interest ones.
                query = f"""
                    MATCH (a:Person {{case_id: $case_id, source_type: 'cellebrite'}})-[:CALLED]->(c:PhoneCall)-[:CALLED_TO]->(b:Person {{case_id: $case_id, source_type: 'cellebrite'}})
                    WHERE a.key IS NOT NULL AND b.key IS NOT NULL {rk_filter_call} {app_filter_call} {date_filter_call}
                    WITH a, b, c.cellebrite_report_key AS rk,
                         collect(c) AS calls
                    WITH a, b, rk,
                         size(calls) AS call_count,
                         reduce(s = 0, cc IN calls | s + coalesce(cc.attachment_count, 0)) AS attach_count,
                         [cc IN calls | cc.timestamp] AS timestamps
                    ORDER BY call_count DESC
                    LIMIT $per_block_cap
                    RETURN a, b, rk, call_count, attach_count, timestamps
                """
                result = session.run(query, params)
                # Neo4j returns one row per (a,b) AND one per (b,a) when both
                # directions exist. We normalise to the sorted pair and merge
                # those two rows into a single thread.
                call_pairs: Dict[str, dict] = {}
                for record in result:
                    a = dict(record["a"])
                    b = dict(record["b"])
                    a_key, b_key = a.get("key"), b.get("key")
                    if not a_key or not b_key:
                        continue
                    # Participant filter (see chat branch for `participant_keys` semantics).
                    if from_keys or to_keys or participant_keys:
                        pkeys = {a_key, b_key}
                        if from_keys and not any(k in pkeys for k in from_keys):
                            continue
                        if to_keys and not any(k in pkeys for k in to_keys):
                            continue
                        if participant_keys and not any(k in pkeys for k in participant_keys):
                            continue

                    pair_keys = tuple(sorted([a_key, b_key]))
                    thread_id = f"calls-{record['rk']}-{pair_keys[0]}-{pair_keys[1]}"
                    timestamps = [t for t in (record["timestamps"] or []) if t]
                    call_count = int(record["call_count"] or 0)
                    attach_count = int(record["attach_count"] or 0)

                    existing = call_pairs.get(thread_id)
                    if existing is None:
                        # Determine participants preserving person metadata
                        participants = [
                            {"key": a_key, "name": a.get("name") or a_key, "is_owner": bool(a.get("is_phone_owner"))},
                            {"key": b_key, "name": b.get("name") or b_key, "is_owner": bool(b.get("is_phone_owner"))},
                        ]
                        # Order participants to match pair_keys ordering
                        participants.sort(key=lambda p: p["key"])
                        name_parts = [p["name"] for p in participants]
                        call_pairs[thread_id] = {
                            "thread_id": thread_id,
                            "thread_type": "calls",
                            "source_app": "Calls",
                            "name": f"Calls: {name_parts[0]} <-> {name_parts[1]}",
                            "participants": participants,
                            "message_count": call_count,
                            "attachment_count": attach_count,
                            "has_attachments": attach_count > 0,
                            "last_activity": max(timestamps) if timestamps else None,
                            "first_activity": min(timestamps) if timestamps else None,
                            "report_key": record["rk"],
                            "pair_keys": list(pair_keys),
                        }
                    else:
                        # Merge the reverse-direction row into the existing one
                        existing["message_count"] += call_count
                        existing["attachment_count"] += attach_count
                        existing["has_attachments"] = existing["attachment_count"] > 0
                        if timestamps:
                            ts_max = max(timestamps)
                            ts_min = min(timestamps)
                            if existing.get("last_activity") is None or ts_max > existing["last_activity"]:
                                existing["last_activity"] = ts_max
                            if existing.get("first_activity") is None or ts_min < existing["first_activity"]:
                                existing["first_activity"] = ts_min

                if len(call_pairs) >= per_block_cap:
                    truncated = True
                threads.extend(call_pairs.values())

            # ---- Synthetic email threads (per participant pair + report) ----
            if "emails" in active_types:
                query = f"""
                    MATCH (a:Person {{case_id: $case_id, source_type: 'cellebrite'}})-[:EMAILED]->(e:Email)-[:SENT_TO]->(b:Person {{case_id: $case_id, source_type: 'cellebrite'}})
                    WHERE a.key IS NOT NULL AND b.key IS NOT NULL {rk_filter_email} {app_filter_email} {date_filter_email}
                    WITH a, b, e.cellebrite_report_key AS rk,
                         collect(e) AS emails
                    WITH a, b, rk,
                         size(emails) AS email_count,
                         reduce(s = 0, ee IN emails | s + coalesce(ee.attachment_count, 0)) AS attach_count,
                         [ee IN emails | ee.timestamp] AS timestamps
                    ORDER BY email_count DESC
                    LIMIT $per_block_cap
                    RETURN a, b, rk, email_count, attach_count, timestamps
                """
                result = session.run(query, params)
                # Same dedupe pattern as calls - merge bidirectional pairs
                email_pairs: Dict[str, dict] = {}
                for record in result:
                    a = dict(record["a"])
                    b = dict(record["b"])
                    a_key, b_key = a.get("key"), b.get("key")
                    if not a_key or not b_key:
                        continue
                    if from_keys or to_keys or participant_keys:
                        pkeys = {a_key, b_key}
                        if from_keys and not any(k in pkeys for k in from_keys):
                            continue
                        if to_keys and not any(k in pkeys for k in to_keys):
                            continue
                        if participant_keys and not any(k in pkeys for k in participant_keys):
                            continue

                    pair_keys = tuple(sorted([a_key, b_key]))
                    thread_id = f"emails-{record['rk']}-{pair_keys[0]}-{pair_keys[1]}"
                    timestamps = [t for t in (record["timestamps"] or []) if t]
                    email_count = int(record["email_count"] or 0)
                    attach_count = int(record["attach_count"] or 0)

                    existing = email_pairs.get(thread_id)
                    if existing is None:
                        participants = [
                            {"key": a_key, "name": a.get("name") or a_key, "is_owner": bool(a.get("is_phone_owner"))},
                            {"key": b_key, "name": b.get("name") or b_key, "is_owner": bool(b.get("is_phone_owner"))},
                        ]
                        participants.sort(key=lambda p: p["key"])
                        name_parts = [p["name"] for p in participants]
                        email_pairs[thread_id] = {
                            "thread_id": thread_id,
                            "thread_type": "emails",
                            "source_app": "Email",
                            "name": f"Emails: {name_parts[0]} <-> {name_parts[1]}",
                            "participants": participants,
                            "message_count": email_count,
                            "attachment_count": attach_count,
                            "has_attachments": attach_count > 0,
                            "last_activity": max(timestamps) if timestamps else None,
                            "first_activity": min(timestamps) if timestamps else None,
                            "report_key": record["rk"],
                            "pair_keys": list(pair_keys),
                        }
                    else:
                        existing["message_count"] += email_count
                        existing["attachment_count"] += attach_count
                        existing["has_attachments"] = existing["attachment_count"] > 0
                        if timestamps:
                            ts_max = max(timestamps)
                            ts_min = min(timestamps)
                            if existing.get("last_activity") is None or ts_max > existing["last_activity"]:
                                existing["last_activity"] = ts_max
                            if existing.get("first_activity") is None or ts_min < existing["first_activity"]:
                                existing["first_activity"] = ts_min

                if len(email_pairs) >= per_block_cap:
                    truncated = True
                threads.extend(email_pairs.values())

        # Merge duplicate synthetic threads (same pair, same report, both directions - already grouped by query)
        # Sort all threads by last_activity DESC
        threads.sort(key=lambda t: (t.get("last_activity") or ""), reverse=True)

        total = len(threads)
        # Apply pagination
        threads = threads[offset: offset + limit]
        return {
            "threads": threads,
            "total": total,
            "truncated": truncated,
            "per_block_cap": per_block_cap,
        }

    def get_cellebrite_thread_detail(
        self,
        case_id: str,
        thread_id: str,
        thread_type: str,
        limit: int = 500,
        offset: int = 0,
        anchor_key: Optional[str] = None,
    ) -> dict:
        """
        Get chronological items (messages/calls/emails) for a thread with sender
        attribution and attachment file IDs.

        When `anchor_key` is given, the effective offset is computed so the
        returned window is centred on that anchor message. This lets a
        caller (e.g. "click a message in Overview Messages -> open the
        whole conversation, scrolled to that bubble") land on the right
        spot even for threads with thousands of items, where the default
        oldest-first slice wouldn't include the anchor.
        """
        items: list = []

        with self._driver.session() as session:
            if thread_type == "chat":
                # Anchor windowing - find the anchor's position in the
                # chat (chronological rank by timestamp ASC) and shift the
                # offset so the window straddles it. Falls back silently
                # to the caller-supplied offset if the anchor isn't found.
                if anchor_key:
                    shifted = self._anchor_window_offset(
                        session,
                        thread_type="chat",
                        case_id=case_id,
                        thread_id=thread_id,
                        anchor_key=anchor_key,
                        limit=limit,
                    )
                    if shifted is not None:
                        offset = shifted

                # Real chat thread - load parent + messages
                result = session.run(
                    """
                    MATCH (chat:Communication {case_id: $case_id, key: $thread_id})
                    OPTIONAL MATCH (p:Person)-[:PARTICIPATED_IN]->(chat)
                    RETURN chat, collect(DISTINCT p) AS participants
                    """,
                    case_id=case_id,
                    thread_id=thread_id,
                )
                record = result.single()
                if not record:
                    return {"thread": None, "items": [], "total": 0}
                chat = dict(record["chat"])
                participants = [dict(p) for p in record["participants"] if p is not None]

                msg_result = session.run(
                    """
                    MATCH (msg:Communication)-[:PART_OF]->(chat:Communication {case_id: $case_id, key: $thread_id})
                    WHERE msg.body IS NOT NULL
                    OPTIONAL MATCH (sender:Person)-[:SENT_MESSAGE]->(msg)
                    RETURN msg, sender
                    ORDER BY msg.timestamp
                    SKIP $offset LIMIT $limit
                    """,
                    case_id=case_id,
                    thread_id=thread_id,
                    offset=offset,
                    limit=limit,
                )
                for r in msg_result:
                    msg = dict(r["msg"])
                    sender = dict(r["sender"]) if r["sender"] else None
                    items.append({
                        "id": msg.get("id"),
                        # Expose the node `key` separately so the rail's
                        # /events/detail/{key} lookup matches the right node.
                        # Communication.id is the source-system id; only
                        # `key` matches the detail endpoint's WHERE clause.
                        "key": msg.get("key"),
                        "type": "message",
                        "timestamp": msg.get("timestamp"),
                        "date": msg.get("date"),
                        "time": msg.get("time"),
                        "source_app": msg.get("source_app"),
                        "message_type": msg.get("message_type"),
                        "body": msg.get("body") or "",
                        "deleted_state": msg.get("deleted_state"),
                        "attachment_file_ids": list(msg.get("attachment_file_ids") or []),
                        "sender": {
                            "key": sender.get("key") if sender else None,
                            "name": sender.get("name") if sender else None,
                            "is_owner": bool(sender.get("is_phone_owner")) if sender else False,
                        } if sender else None,
                    })

                # Total count for pagination
                total_r = session.run(
                    """
                    MATCH (msg:Communication)-[:PART_OF]->(chat:Communication {case_id: $case_id, key: $thread_id})
                    WHERE msg.body IS NOT NULL
                    RETURN count(msg) AS n
                    """,
                    case_id=case_id,
                    thread_id=thread_id,
                ).single()
                total = int(total_r["n"]) if total_r else 0

                return {
                    "thread": {
                        "thread_id": thread_id,
                        "thread_type": "chat",
                        "name": chat.get("name"),
                        "source_app": chat.get("source_app"),
                        "participants": [
                            {
                                "key": p.get("key"),
                                "name": p.get("name") or p.get("key"),
                                "is_owner": bool(p.get("is_phone_owner")),
                            }
                            for p in participants
                        ],
                        "report_key": chat.get("cellebrite_report_key"),
                    },
                    "items": items,
                    "total": total,
                }

            elif thread_type == "calls" or thread_type == "emails":
                # Parse thread_id "calls-{report_key}-{keyA}-{keyB}" or "emails-..."
                # Note: report_key may contain dashes; split on first & last 2 segments
                if not thread_id.startswith(f"{thread_type}-"):
                    return {"thread": None, "items": [], "total": 0}
                remainder = thread_id[len(thread_type) + 1:]
                # Participant keys are prefixed with phone-/email-/... and may contain dashes.
                # We split from the right: the last TWO tokens that start with a known person-key prefix
                # are the pair. Everything before = report_key.
                parts = remainder.split("-")
                # Reconstruct: scan from right until we have two person keys.
                # Person keys look like phone-XXXXXX, email-xxx, or app-slug-id.
                # Heuristic: split into report_key + keyA + keyB by scanning for prefix markers.
                # Simpler: store dashless separator would be cleaner; here we use known person-key prefixes.
                def find_person_key_start(tokens, start_idx):
                    prefixes = ("phone", "email", "fb", "ig", "wa", "tg", "snap", "twitter", "linkedin")
                    for i in range(start_idx, len(tokens)):
                        for pfx in prefixes:
                            if tokens[i] == pfx:
                                return i
                    return -1

                # Find two person-key start indices
                key_a_start = find_person_key_start(parts, 0)
                key_b_start = find_person_key_start(parts, key_a_start + 1) if key_a_start >= 0 else -1
                if key_a_start < 0 or key_b_start < 0:
                    return {"thread": None, "items": [], "total": 0}

                report_key = "-".join(parts[:key_a_start])
                key_a = "-".join(parts[key_a_start:key_b_start])
                key_b = "-".join(parts[key_b_start:])

                if thread_type == "calls":
                    query = """
                        MATCH (a:Person {case_id: $case_id, key: $key_a})
                        MATCH (b:Person {case_id: $case_id, key: $key_b})
                        MATCH (src:Person)-[:CALLED]->(c:PhoneCall)-[:CALLED_TO]->(dst:Person)
                        WHERE c.cellebrite_report_key = $report_key
                          AND ((src = a AND dst = b) OR (src = b AND dst = a))
                        RETURN c, src, dst
                        ORDER BY c.timestamp
                        SKIP $offset LIMIT $limit
                    """
                    result = session.run(
                        query,
                        case_id=case_id,
                        key_a=key_a,
                        key_b=key_b,
                        report_key=report_key,
                        offset=offset,
                        limit=limit,
                    )
                    for r in result:
                        c = dict(r["c"])
                        src = dict(r["src"]) if r["src"] else None
                        dst = dict(r["dst"]) if r["dst"] else None
                        items.append({
                            "id": c.get("id"),
                            "key": c.get("key"),
                            "type": "call",
                            "timestamp": c.get("timestamp"),
                            "date": c.get("date"),
                            "time": c.get("time"),
                            "source_app": c.get("source_app"),
                            "direction": c.get("direction"),
                            "duration": c.get("duration"),
                            "call_type": c.get("call_type"),
                            "video_call": bool(c.get("video_call")),
                            "deleted_state": c.get("deleted_state"),
                            "attachment_file_ids": list(c.get("attachment_file_ids") or []),
                            "sender": {
                                "key": src.get("key") if src else None,
                                "name": src.get("name") if src else None,
                                "is_owner": bool(src.get("is_phone_owner")) if src else False,
                            } if src else None,
                            "recipient": {
                                "key": dst.get("key") if dst else None,
                                "name": dst.get("name") if dst else None,
                                "is_owner": bool(dst.get("is_phone_owner")) if dst else False,
                            } if dst else None,
                        })
                else:  # emails
                    query = """
                        MATCH (a:Person {case_id: $case_id, key: $key_a})
                        MATCH (b:Person {case_id: $case_id, key: $key_b})
                        MATCH (src:Person)-[:EMAILED]->(e:Email)-[:SENT_TO]->(dst:Person)
                        WHERE e.cellebrite_report_key = $report_key
                          AND ((src = a AND dst = b) OR (src = b AND dst = a))
                        RETURN e, src, dst
                        ORDER BY e.timestamp
                        SKIP $offset LIMIT $limit
                    """
                    result = session.run(
                        query,
                        case_id=case_id,
                        key_a=key_a,
                        key_b=key_b,
                        report_key=report_key,
                        offset=offset,
                        limit=limit,
                    )
                    for r in result:
                        e = dict(r["e"])
                        src = dict(r["src"]) if r["src"] else None
                        dst = dict(r["dst"]) if r["dst"] else None
                        items.append({
                            "id": e.get("id"),
                            "key": e.get("key"),
                            "type": "email",
                            "timestamp": e.get("timestamp"),
                            "date": e.get("date"),
                            "time": e.get("time"),
                            "source_app": e.get("source_app"),
                            "subject": e.get("subject"),
                            "body": e.get("body") or "",
                            "folder": e.get("folder"),
                            "email_status": e.get("email_status"),
                            "deleted_state": e.get("deleted_state"),
                            "attachment_file_ids": list(e.get("attachment_file_ids") or []),
                            "sender": {
                                "key": src.get("key") if src else None,
                                "name": src.get("name") if src else None,
                                "is_owner": bool(src.get("is_phone_owner")) if src else False,
                            } if src else None,
                            "recipient": {
                                "key": dst.get("key") if dst else None,
                                "name": dst.get("name") if dst else None,
                                "is_owner": bool(dst.get("is_phone_owner")) if dst else False,
                            } if dst else None,
                        })

                # Name lookup for thread metadata
                a_r = session.run(
                    "MATCH (p:Person {case_id: $case_id, key: $key}) RETURN p LIMIT 1",
                    case_id=case_id,
                    key=key_a,
                ).single()
                b_r = session.run(
                    "MATCH (p:Person {case_id: $case_id, key: $key}) RETURN p LIMIT 1",
                    case_id=case_id,
                    key=key_b,
                ).single()
                a = dict(a_r["p"]) if a_r else {}
                b = dict(b_r["p"]) if b_r else {}

                return {
                    "thread": {
                        "thread_id": thread_id,
                        "thread_type": thread_type,
                        "name": f"{a.get('name') or key_a} <-> {b.get('name') or key_b}",
                        "source_app": "Calls" if thread_type == "calls" else "Email",
                        "participants": [
                            {"key": key_a, "name": a.get("name") or key_a, "is_owner": bool(a.get("is_phone_owner"))},
                            {"key": key_b, "name": b.get("name") or key_b, "is_owner": bool(b.get("is_phone_owner"))},
                        ],
                        "report_key": report_key,
                    },
                    "items": items,
                    "total": len(items),
                }

            else:
                return {"thread": None, "items": [], "total": 0}

    def _anchor_window_offset(
        self,
        session,
        thread_type: str,
        case_id: str,
        thread_id: str,
        anchor_key: str,
        limit: int,
    ) -> Optional[int]:
        """
        Find a SKIP offset that centres a `limit`-sized window on the
        anchor message inside a thread. Returns None when the anchor
        can't be located (caller falls back to its original offset).

        Currently used for chat threads only - calls/emails threads are
        pair-bounded and rarely large enough to need windowing.
        """
        if thread_type != "chat":
            return None
        # One round-trip to learn how many sibling messages come BEFORE
        # the anchor in timestamp ASC order. Counting on the database
        # side keeps the response payload tiny.
        rec = session.run(
            """
            MATCH (anchor:Communication {case_id: $case_id, key: $anchor_key})
                  -[:PART_OF]->(chat:Communication {case_id: $case_id, key: $thread_id})
            WHERE anchor.body IS NOT NULL
            WITH anchor.timestamp AS ts, anchor.key AS aks
            MATCH (m:Communication)-[:PART_OF]->(:Communication {case_id: $case_id, key: $thread_id})
            WHERE m.body IS NOT NULL
              AND (m.timestamp < ts OR (m.timestamp = ts AND m.key < aks))
            RETURN count(m) AS before
            """,
            case_id=case_id,
            thread_id=thread_id,
            anchor_key=anchor_key,
        ).single()
        if not rec:
            return None
        before = int(rec["before"])
        # Place the anchor a bit above the centre so the user sees the
        # message they clicked plus more context after it (i.e. the next
        # part of the conversation).
        return max(0, before - max(1, limit // 3))

    def get_cellebrite_comms_between(
        self,
        case_id: str,
        from_keys: Optional[List[str]] = None,
        to_keys: Optional[List[str]] = None,
        participant_keys: Optional[List[str]] = None,
        types: Optional[List[str]] = None,
        report_keys: Optional[List[str]] = None,
        source_apps: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
        sort: str = "desc",
        cursor: Optional[str] = None,
    ) -> dict:
        """
        Get chronological cross-type comms where any from_keys participant
        communicated with any to_keys participant (AND semantics).

        types:  subset of ['message', 'call', 'email'] - includes all if None.
        sort:   'desc' (newest first) or 'asc' (oldest first). Drives both
                the per-type ORDER BY and the post-merge sort so the row
                cap interacts correctly with the user's chosen direction.
        cursor: opaque page-continuation token from a previous response's
                `next_cursor`. When supplied, takes priority over `offset`
                and triggers per-type keyset pagination - each branch's
                WHERE adds `(ts < cursor_ts OR (ts = cursor_ts AND id <
                cursor_id))` (or > for asc), so deep pages don't re-read
                the rows already returned. With keyset, the per-type
                fetch grabs `limit` rows; without it (legacy callers
                still using offset), it grabs `limit + offset` like
                before.

        The cursor is base64(JSON({type: (ts, id)})). Encoding is
        per-type so a page that came from messages-only doesn't
        accidentally short-circuit calls/emails on the next page.
        """
        active_types = set(types) if types else {"message", "call", "email"}
        sort_dir = "ASC" if (sort or "").lower() == "asc" else "DESC"
        reverse_sort = sort_dir == "DESC"

        # Decode the per-type cursor if present. Anything malformed is
        # treated as no-cursor - the user gets a fresh page rather than
        # an error. Cursors get invalidated implicitly when filters
        # change (the server returns new ones; the old token simply
        # corresponds to a different filter context and the page may
        # contain duplicates with what's already on screen, which is
        # acceptable degradation).
        per_type_cursor: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
        if cursor:
            try:
                decoded = json.loads(base64.b64decode(cursor.encode("ascii")).decode("utf-8"))
                if isinstance(decoded, dict):
                    for k, v in decoded.items():
                        if isinstance(v, list) and len(v) == 2:
                            per_type_cursor[k] = (v[0], v[1])
            except Exception:
                per_type_cursor = {}

        params: Dict[str, Any] = {"case_id": case_id}
        params["from_keys"] = list(from_keys) if from_keys else []
        params["to_keys"] = list(to_keys) if to_keys else []
        # Involvement (OR) keys. Used by Filter Comms intents and the
        # "Any direction" participants mode. Empty list = no involvement
        # filter; otherwise sender OR recipient must be in the set -
        # solves the "Filter Comms by one contact returns nothing"
        # bug where the same key in both from_keys and to_keys collapsed
        # to "sender == recipient" (i.e. self-msgs only).
        params["participant_keys"] = list(participant_keys) if participant_keys else []
        rk_filter_msg = ""
        rk_filter_call = ""
        rk_filter_email = ""
        if report_keys:
            rk_filter_msg = "AND msg.cellebrite_report_key IN $report_keys"
            rk_filter_call = "AND c.cellebrite_report_key IN $report_keys"
            rk_filter_email = "AND e.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        app_filter_msg = ""
        app_filter_call = ""
        app_filter_email = ""
        if source_apps:
            app_filter_msg = "AND msg.source_app IN $source_apps"
            app_filter_call = "AND c.source_app IN $source_apps"
            app_filter_email = "AND e.source_app IN $source_apps"
            params["source_apps"] = list(source_apps)

        date_filter_msg = ""
        date_filter_call = ""
        date_filter_email = ""
        sd = _normalize_date_bound(start_date)
        ed = _normalize_date_bound(end_date)
        if sd:
            # Compare on the writer-normalized `date` field where present;
            # fall back to the raw timestamp string only if `date` is absent.
            # This eliminates the "2022 data appearing in newer windows"
            # bug caused by inconsistent timestamp formats across source apps.
            date_filter_msg = " AND coalesce(msg.date, msg.timestamp, '') >= $start_date"
            date_filter_call = " AND coalesce(c.date, c.timestamp, '') >= $start_date"
            date_filter_email = " AND coalesce(e.date, e.timestamp, '') >= $start_date"
            params["start_date"] = sd
        if ed:
            date_filter_msg += " AND coalesce(msg.date, msg.timestamp, '') <= $end_date"
            date_filter_call += " AND coalesce(c.date, c.timestamp, '') <= $end_date"
            date_filter_email += " AND coalesce(e.date, e.timestamp, '') <= $end_date"
            params["end_date"] = ed

        items: list = []

        # Per-type cursor WHERE fragments. When a cursor for a type is
        # set we narrow the per-type fetch to "rows beyond the cursor"
        # and pull only `limit` rows (instead of `limit + offset`). When
        # no cursor (legacy callers using offset), we keep the
        # offset-style budget so SKIP/OFFSET behaviour is unchanged.
        # The (ts, id) tuple guarantees deterministic ordering even
        # when two events share a timestamp - id breaks the tie.
        def _cursor_clause(kind: str, ts_expr: str, id_expr: str) -> str:
            cur = per_type_cursor.get(kind)
            if not cur or not cur[0]:
                return ""
            cmp = "<" if sort_dir == "DESC" else ">"
            return (
                f" AND ({ts_expr} {cmp} ${kind}_cur_ts"
                f" OR ({ts_expr} = ${kind}_cur_ts AND coalesce({id_expr}, '') {cmp} ${kind}_cur_id))"
            )

        for kind, (cur_ts, cur_id) in per_type_cursor.items():
            if cur_ts is not None:
                params[f"{kind}_cur_ts"] = cur_ts
                params[f"{kind}_cur_id"] = cur_id or ""

        # When a cursor is in play, each per-type fetch only needs `limit`
        # rows (not limit+offset) because keyset already excludes the
        # earlier pages. Falls back to the offset budget for legacy
        # callers that haven't migrated yet.
        per_type_budget = limit if cursor else (limit + offset)

        # Run all three type-specific queries inside ONE read transaction
        # so they share a single round-trip to Neo4j. The previous code
        # opened three independent session.run() calls, paying RTT cost
        # three times per page load. Composite indexes added in commit
        # fbe8df0 (case_id + cellebrite_report_key) keep each query
        # cheap; combining them here cuts the wall-clock latency users
        # see on the deployed env. Session/tx lifecycle is managed
        # manually instead of via `with` because we need the tx to span
        # all three branches before commit.
        session = self._driver.session()
        tx = session.begin_transaction()
        try:
            if "message" in active_types:
                # Messages: sender -> message -> chat <- participants (includes recipient).
                #
                # Involvement (`participant_keys`) is OR over sender + recipient: the
                # message qualifies if the sender is in the set OR any participant in
                # the chat (other than sender) is. This is the fix for "Filter Comms
                # by one contact returns nothing" - previously the same key in
                # from_keys + to_keys forced sender == recipient.
                msg_cursor_clause = _cursor_clause("message", "msg.timestamp", "msg.id")
                query = f"""
                    MATCH (sender:Person)-[:SENT_MESSAGE]->(msg:Communication)-[:PART_OF]->(chat:Communication)
                    WHERE msg.case_id = $case_id AND msg.body IS NOT NULL
                      AND (size($from_keys) = 0 OR sender.key IN $from_keys)
                      {rk_filter_msg} {app_filter_msg} {date_filter_msg}
                      {msg_cursor_clause}
                    MATCH (recipient:Person)-[:PARTICIPATED_IN]->(chat)
                    WHERE recipient <> sender
                      AND (size($to_keys) = 0 OR recipient.key IN $to_keys)
                    WITH msg, sender, chat,
                         collect(DISTINCT recipient) AS recipients
                    WHERE size($participant_keys) = 0
                       OR sender.key IN $participant_keys
                       OR ANY(rp IN recipients WHERE rp.key IN $participant_keys)
                    RETURN msg, sender, recipients, chat
                    ORDER BY msg.timestamp {sort_dir}
                    LIMIT $limit
                """
                result = tx.run(query, {**params, "limit": per_type_budget})
                for r in result:
                    msg = dict(r["msg"])
                    sender = dict(r["sender"]) if r["sender"] else None
                    chat = dict(r["chat"])
                    recipients = [dict(rp) for rp in r["recipients"] if rp is not None]
                    items.append({
                        "id": msg.get("id"),
                        "type": "message",
                        "timestamp": msg.get("timestamp"),
                        "source_app": msg.get("source_app"),
                        "message_type": msg.get("message_type"),
                        "body": msg.get("body") or "",
                        "attachment_file_ids": list(msg.get("attachment_file_ids") or []),
                        "thread_id": chat.get("key"),
                        "thread_type": "chat",
                        "sender": {
                            "key": sender.get("key"),
                            "name": sender.get("name") or sender.get("key"),
                            "is_owner": bool(sender.get("is_phone_owner")),
                        } if sender else None,
                        "recipients": [
                            {"key": rp.get("key"), "name": rp.get("name") or rp.get("key")}
                            for rp in recipients
                        ],
                        "report_key": msg.get("cellebrite_report_key"),
                    })

            if "call" in active_types:
                call_cursor_clause = _cursor_clause("call", "c.timestamp", "c.id")
                query = f"""
                    MATCH (src:Person)-[:CALLED]->(c:PhoneCall)-[:CALLED_TO]->(dst:Person)
                    WHERE c.case_id = $case_id
                      AND (
                          (size($from_keys) = 0 OR src.key IN $from_keys)
                          AND (size($to_keys) = 0 OR dst.key IN $to_keys)
                      )
                      AND (
                          size($participant_keys) = 0
                          OR src.key IN $participant_keys
                          OR dst.key IN $participant_keys
                      )
                      {rk_filter_call} {app_filter_call} {date_filter_call}
                      {call_cursor_clause}
                    RETURN c, src, dst
                    ORDER BY c.timestamp {sort_dir}
                    LIMIT $limit
                """
                result = tx.run(query, {**params, "limit": per_type_budget})
                for r in result:
                    c = dict(r["c"])
                    src = dict(r["src"]) if r["src"] else None
                    dst = dict(r["dst"]) if r["dst"] else None
                    items.append({
                        "id": c.get("id"),
                        "type": "call",
                        "timestamp": c.get("timestamp"),
                        "source_app": c.get("source_app"),
                        "direction": c.get("direction"),
                        "duration": c.get("duration"),
                        "call_type": c.get("call_type"),
                        "video_call": bool(c.get("video_call")),
                        "attachment_file_ids": list(c.get("attachment_file_ids") or []),
                        "thread_id": None,
                        "thread_type": "calls",
                        "sender": {
                            "key": src.get("key"),
                            "name": src.get("name") or src.get("key"),
                            "is_owner": bool(src.get("is_phone_owner")),
                        } if src else None,
                        "recipients": [
                            {"key": dst.get("key"), "name": dst.get("name") or dst.get("key")}
                        ] if dst else [],
                        "report_key": c.get("cellebrite_report_key"),
                    })

            if "email" in active_types:
                email_cursor_clause = _cursor_clause("email", "e.timestamp", "e.id")
                query = f"""
                    MATCH (src:Person)-[:EMAILED]->(e:Email)-[:SENT_TO]->(dst:Person)
                    WHERE e.case_id = $case_id
                      AND (
                          (size($from_keys) = 0 OR src.key IN $from_keys)
                          AND (size($to_keys) = 0 OR dst.key IN $to_keys)
                      )
                      AND (
                          size($participant_keys) = 0
                          OR src.key IN $participant_keys
                          OR dst.key IN $participant_keys
                      )
                      {rk_filter_email} {app_filter_email} {date_filter_email}
                      {email_cursor_clause}
                    RETURN e, src, dst
                    ORDER BY e.timestamp {sort_dir}
                    LIMIT $limit
                """
                result = tx.run(query, {**params, "limit": per_type_budget})
                for r in result:
                    e = dict(r["e"])
                    src = dict(r["src"]) if r["src"] else None
                    dst = dict(r["dst"]) if r["dst"] else None
                    items.append({
                        "id": e.get("id"),
                        "type": "email",
                        "timestamp": e.get("timestamp"),
                        "source_app": e.get("source_app"),
                        "subject": e.get("subject"),
                        "body": e.get("body") or "",
                        "folder": e.get("folder"),
                        "attachment_file_ids": list(e.get("attachment_file_ids") or []),
                        "thread_id": None,
                        "thread_type": "emails",
                        "sender": {
                            "key": src.get("key"),
                            "name": src.get("name") or src.get("key"),
                            "is_owner": bool(src.get("is_phone_owner")),
                        } if src else None,
                        "recipients": [
                            {"key": dst.get("key"), "name": dst.get("name") or dst.get("key")}
                        ] if dst else [],
                        "report_key": e.get("cellebrite_report_key"),
                    })
            tx.commit()
        except Exception:
            tx.rollback()
            raise
        finally:
            session.close()

        # Dedupe - the same message can be returned multiple times when a
        # chat has many participants and the from/to filters overlap. Keep the
        # first occurrence (keys in the Python dict preserve insertion order).
        seen_ids = set()
        deduped = []
        for it in items:
            key = it.get("id") or it.get("node_key")
            if key is None:
                deduped.append(it)
                continue
            if key in seen_ids:
                continue
            seen_ids.add(key)
            deduped.append(it)
        items = deduped

        # Sort the merged items chronologically. Two passes:
        # (1) compute the page slice for the response, (2) compute the
        # per-type "last seen" used to build next_cursor.
        items.sort(key=lambda i: (i.get("timestamp") or ""), reverse=reverse_sort)
        total = len(items)

        if cursor:
            # Cursor mode: skip the manual offset (already accounted for
            # by the per-type cursor predicates) and just trim to limit.
            page = items[:limit]
        else:
            page = items[offset: offset + limit]

        # Build the next_cursor from the LAST item per type within the
        # page. If a type contributed zero rows to this page, its cursor
        # is dropped - the next request will re-evaluate that type fresh
        # against the same filters. Returning None for next_cursor when
        # there's clearly no more data avoids the client looping.
        last_per_type: Dict[str, Tuple[str, str]] = {}
        for it in page:
            t = it.get("type")
            ts = it.get("timestamp") or ""
            iid = it.get("id") or ""
            if not t or not ts:
                continue
            # Each type's "last seen" is whichever item is furthest in
            # the sort direction within the page - that's the bottom of
            # the page in DESC mode (oldest of the visible rows for
            # that type).
            last_per_type[t] = (ts, iid)

        # We're plausibly out of rows when the page is short (< limit
        # before merging eats space). Be conservative and emit a cursor
        # whenever the merged page filled.
        next_cursor: Optional[str] = None
        if last_per_type and len(page) >= limit:
            payload = {k: [v[0], v[1]] for k, v in last_per_type.items()}
            next_cursor = base64.b64encode(
                json.dumps(payload, separators=(",", ":")).encode("utf-8")
            ).decode("ascii")

        return {
            "items": page,
            "total": total,
            "next_cursor": next_cursor,
        }

    def get_cellebrite_comms_envelope(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
        from_keys: Optional[List[str]] = None,
        to_keys: Optional[List[str]] = None,
        participant_keys: Optional[List[str]] = None,
        types: Optional[List[str]] = None,
        source_apps: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """
        Cheap aggregation across the comms feed shape: total count,
        per-type counts, min/max date, and a per-day histogram.

        Powers the timeline scrubber's "honest" min/max + density curve
        without forcing the client to load any item rows. The point is
        to render the scrubber + tab counts BEFORE any feed pages
        arrive, then page the body separately via /comms/between.

        Cypher does the heavy lifting in three small UNION ALL legs
        (one per type) - each leg returns one (date, count) row per
        distinct date, gated by the same filters /comms/between uses
        so the envelope is always consistent with what the body fetch
        would return.
        """
        active_types = set(types or ["message", "call", "email"])

        # Build shared params + per-type filter fragments. Date bounds
        # use the same normalizer + coalesce(date, timestamp) trick the
        # body fetch uses so the envelope is honest about exclusions.
        params: Dict[str, Any] = {"case_id": case_id}
        rk_filter_msg = ""
        rk_filter_call = ""
        rk_filter_email = ""
        if report_keys:
            rk_filter_msg = " AND msg.cellebrite_report_key IN $report_keys"
            rk_filter_call = " AND c.cellebrite_report_key IN $report_keys"
            rk_filter_email = " AND e.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        from_filter_msg = from_filter_call = from_filter_email = ""
        if from_keys:
            from_filter_msg = " AND sender.key IN $from_keys"
            from_filter_call = " AND src.key IN $from_keys"
            from_filter_email = " AND a.key IN $from_keys"
            params["from_keys"] = list(from_keys)

        to_filter_msg = to_filter_call = to_filter_email = ""
        if to_keys:
            to_filter_msg = " AND recipient.key IN $to_keys"
            to_filter_call = " AND dst.key IN $to_keys"
            to_filter_email = " AND b.key IN $to_keys"
            params["to_keys"] = list(to_keys)

        # Involvement (OR) filter - same semantics as in
        # get_cellebrite_comms_between. Keeps the envelope consistent
        # with the body fetch when callers use the "Any direction" /
        # Filter Comms intent.
        inv_filter_msg = inv_filter_call = inv_filter_email = ""
        if participant_keys:
            inv_filter_msg = " AND (sender.key IN $participant_keys OR recipient.key IN $participant_keys)"
            inv_filter_call = " AND (src.key IN $participant_keys OR dst.key IN $participant_keys)"
            inv_filter_email = " AND (a.key IN $participant_keys OR b.key IN $participant_keys)"
            params["participant_keys"] = list(participant_keys)

        app_filter_msg = app_filter_call = app_filter_email = ""
        if source_apps:
            app_filter_msg = " AND msg.source_app IN $source_apps"
            app_filter_call = " AND c.source_app IN $source_apps"
            app_filter_email = " AND e.source_app IN $source_apps"
            params["source_apps"] = list(source_apps)

        date_filter_msg = date_filter_call = date_filter_email = ""
        sd = _normalize_date_bound(start_date)
        ed = _normalize_date_bound(end_date)
        if sd:
            date_filter_msg = " AND coalesce(msg.date, msg.timestamp, '') >= $start_date"
            date_filter_call = " AND coalesce(c.date, c.timestamp, '') >= $start_date"
            date_filter_email = " AND coalesce(e.date, e.timestamp, '') >= $start_date"
            params["start_date"] = sd
        if ed:
            date_filter_msg += " AND coalesce(msg.date, msg.timestamp, '') <= $end_date"
            date_filter_call += " AND coalesce(c.date, c.timestamp, '') <= $end_date"
            date_filter_email += " AND coalesce(e.date, e.timestamp, '') <= $end_date"
            params["end_date"] = ed

        type_counts = {"message": 0, "call": 0, "email": 0}
        # Histogram is per-day -> frontend may downsample. Server returns
        # the raw day buckets so the same payload feeds both a coarse
        # scrubber and a fine zoom-in.
        per_day: Dict[str, int] = {}
        min_date: Optional[str] = None
        max_date: Optional[str] = None

        with self._driver.session() as session:
            if "message" in active_types:
                cypher = f"""
                    MATCH (sender:Person)-[:SENT_MESSAGE]->(msg:Communication)-[:PART_OF]->(chat:Communication)
                    MATCH (recipient:Person)-[:PARTICIPATED_IN]->(chat)
                    WHERE msg.case_id = $case_id
                      AND msg.source_type = 'cellebrite'
                      AND coalesce(msg.date, msg.timestamp, '') <> ''
                      {rk_filter_msg}{from_filter_msg}{to_filter_msg}{inv_filter_msg}
                      {app_filter_msg}{date_filter_msg}
                    WITH coalesce(msg.date, substring(msg.timestamp, 0, 10)) AS d, msg
                    RETURN d, count(DISTINCT msg) AS c
                """
                rs = session.run(cypher, **params)
                for r in rs:
                    d = r["d"]
                    c = r["c"]
                    if not d:
                        continue
                    type_counts["message"] += c
                    per_day[d] = per_day.get(d, 0) + c
                    if min_date is None or d < min_date:
                        min_date = d
                    if max_date is None or d > max_date:
                        max_date = d

            if "call" in active_types:
                cypher = f"""
                    MATCH (src:Person)-[:CALLED]->(c:PhoneCall)-[:CALLED_TO]->(dst:Person)
                    WHERE c.case_id = $case_id
                      AND c.source_type = 'cellebrite'
                      AND coalesce(c.date, c.timestamp, '') <> ''
                      {rk_filter_call}{from_filter_call}{to_filter_call}{inv_filter_call}
                      {app_filter_call}{date_filter_call}
                    WITH coalesce(c.date, substring(c.timestamp, 0, 10)) AS d, c
                    RETURN d, count(DISTINCT c) AS cnt
                """
                rs = session.run(cypher, **params)
                for r in rs:
                    d = r["d"]
                    cnt = r["cnt"]
                    if not d:
                        continue
                    type_counts["call"] += cnt
                    per_day[d] = per_day.get(d, 0) + cnt
                    if min_date is None or d < min_date:
                        min_date = d
                    if max_date is None or d > max_date:
                        max_date = d

            if "email" in active_types:
                cypher = f"""
                    MATCH (a:Person)-[:EMAILED]->(e:Email)-[:SENT_TO]->(b:Person)
                    WHERE e.case_id = $case_id
                      AND e.source_type = 'cellebrite'
                      AND coalesce(e.date, e.timestamp, '') <> ''
                      {rk_filter_email}{from_filter_email}{to_filter_email}{inv_filter_email}
                      {app_filter_email}{date_filter_email}
                    WITH coalesce(e.date, substring(e.timestamp, 0, 10)) AS d, e
                    RETURN d, count(DISTINCT e) AS cnt
                """
                rs = session.run(cypher, **params)
                for r in rs:
                    d = r["d"]
                    cnt = r["cnt"]
                    if not d:
                        continue
                    type_counts["email"] += cnt
                    per_day[d] = per_day.get(d, 0) + cnt
                    if min_date is None or d < min_date:
                        min_date = d
                    if max_date is None or d > max_date:
                        max_date = d

        total = type_counts["message"] + type_counts["call"] + type_counts["email"]

        # Sort the histogram chronologically so the client doesn't have
        # to. Days with zero count are absent - frontend bridges them
        # when rendering the bar chart.
        hist = [
            {"date": d, "count": c}
            for d, c in sorted(per_day.items())
        ]

        return {
            "total": total,
            "type_counts": type_counts,
            "min_date": min_date,
            "max_date": max_date,
            "histogram": hist,
        }

    def search_cellebrite_comms_messages(
        self,
        case_id: str,
        query: str,
        report_keys: Optional[List[str]] = None,
        limit: int = 200,
    ) -> dict:
        """
        Full-text search across message bodies, email subjects/bodies and
        call notes for the case. Returns the distinct thread_ids that
        contain a match plus a ranked list of message snippets.

        Frontend uses this to:
          1. narrow the thread list to threads-that-mention-the-term, and
          2. auto-open the first matching thread scrolled to the message.

        Match algorithm: case-insensitive substring on `body`, `subject`,
        and `name` of Communication / Email / PhoneCall nodes tagged
        with cellebrite source_type and within the requested phones.

        The returned snippet is the literal matched text plus up to 60
        chars of context on either side, so the frontend can render a
        preview without re-fetching the full message body.
        """
        q = (query or "").strip()
        if not q:
            return {"query": "", "thread_ids": [], "matches": [], "total": 0}
        # Guard against absurdly long queries - anything past ~200 chars is
        # almost certainly a paste mishap, and very long CONTAINS predicates
        # explode Neo4j's substring scan cost on body text. Truncate rather
        # than reject so the user still gets a useful result.
        if len(q) > 200:
            q = q[:200]

        params: Dict[str, Any] = {
            "case_id": case_id,
            "q_lower": q.lower(),
        }
        rk_filter = ""
        if report_keys:
            rk_filter = " AND m.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        # Match Communication (chat / message) nodes - substring on body
        # OR subject OR name. We pull the message + its parent chat (so we
        # can return the parent thread_id, which is what the UI lists).
        cypher = f"""
            MATCH (m:Communication {{case_id: $case_id, source_type: 'cellebrite'}})
            WHERE (
                (m.body IS NOT NULL AND toLower(m.body) CONTAINS $q_lower)
                OR (m.subject IS NOT NULL AND toLower(m.subject) CONTAINS $q_lower)
                OR (m.name IS NOT NULL AND toLower(m.name) CONTAINS $q_lower)
            ){rk_filter}
            OPTIONAL MATCH (m)-[:PART_OF]->(parent:Communication)
            WITH m,
                 coalesce(parent.key, m.key) AS thread_key,
                 coalesce(parent.source_app, m.source_app) AS source_app,
                 coalesce(parent.cellebrite_report_key, m.cellebrite_report_key) AS report_key
            RETURN m.key AS message_id,
                   m.body AS body,
                   m.subject AS subject,
                   m.name AS name,
                   m.timestamp AS timestamp,
                   thread_key,
                   source_app,
                   report_key
            ORDER BY m.timestamp DESC
            LIMIT $limit
        """
        params["limit"] = limit

        matches = []
        thread_ids: list = []
        seen_threads = set()
        with self._driver.session() as session:
            for rec in session.run(cypher, **params):
                tk = rec["thread_key"]
                snippet = _build_match_snippet(
                    rec.get("body") or rec.get("subject") or rec.get("name") or "",
                    q,
                )
                matches.append({
                    "message_id": rec.get("message_id"),
                    "thread_id": tk,
                    "thread_type": "chat",
                    "timestamp": rec.get("timestamp"),
                    "source_app": rec.get("source_app"),
                    "report_key": rec.get("report_key"),
                    "snippet": snippet,
                })
                if tk and tk not in seen_threads:
                    seen_threads.add(tk)
                    thread_ids.append(tk)

        return {
            "query": q,
            "thread_ids": thread_ids,
            "matches": matches,
            "total": len(matches),
        }

    def _build_event_filters(
        self,
        report_keys: Optional[List[str]],
        start_date: Optional[str],
        end_date: Optional[str],
        source_apps: Optional[List[str]],
        prefix: str = "n",
        place: Optional[str] = None,
        near: Optional[Tuple[float, float, float]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Build a shared WHERE fragment for event queries.

        place: substring (case-insensitive) matched against the
               reverse-geocoded fields stamped by G4. Items without
               geocode info fail closed - the user asked a place
               question, the rows we keep have place answers.
        near:  (lat, lng, radius_meters). Filters by haversine
               distance from the centre, computed in Cypher via
               point.distance() (Neo4j 5+).
        """
        parts = [f"{prefix}.case_id = $case_id"]
        params: Dict[str, Any] = {}
        if report_keys:
            parts.append(f"{prefix}.cellebrite_report_key IN $report_keys")
            params["report_keys"] = list(report_keys)
        sd = _normalize_date_bound(start_date)
        ed = _normalize_date_bound(end_date)
        if sd:
            # Compare against `date` (YYYY-MM-DD) where present, falling
            # back to the raw `timestamp` string. Mixed timestamp formats
            # across source apps (some with timezone, some without) made
            # the previous direct timestamp comparison unreliable.
            parts.append(f"coalesce({prefix}.date, {prefix}.timestamp, '') >= $start_date")
            params["start_date"] = sd
        if ed:
            parts.append(f"coalesce({prefix}.date, {prefix}.timestamp, '') <= $end_date")
            params["end_date"] = ed
        if source_apps:
            parts.append(f"{prefix}.source_app IN $source_apps")
            params["source_apps"] = list(source_apps)
        if place:
            # OR across the geocoded fields so a single substring
            # matches whichever level of the address pyramid carries
            # it. toLower keeps the comparison case-insensitive.
            place_lower = str(place).strip().lower()
            if place_lower:
                parts.append(
                    "("
                    f"toLower(coalesce({prefix}.address, '')) CONTAINS $place_q"
                    f" OR toLower(coalesce({prefix}.place_name, '')) CONTAINS $place_q"
                    f" OR toLower(coalesce({prefix}.country, '')) CONTAINS $place_q"
                    f" OR toLower(coalesce({prefix}.country_code, '')) CONTAINS $place_q"
                    f" OR toLower(coalesce({prefix}.admin1, '')) CONTAINS $place_q"
                    f" OR toLower(coalesce({prefix}.admin2, '')) CONTAINS $place_q"
                    ")"
                )
                params["place_q"] = place_lower
        if near:
            lat, lng, radius_m = near
            try:
                lat_f = float(lat); lng_f = float(lng); rad_f = float(radius_m)
            except (TypeError, ValueError):
                lat_f = lng_f = rad_f = None
            if lat_f is not None and rad_f and rad_f > 0:
                # point.distance() works on Neo4j 5; the values are
                # WGS84 points so distance is metres without further
                # conversion. The not-null guard avoids an IS NOT NULL
                # comparison error on points that were never set.
                parts.append(
                    f"{prefix}.latitude IS NOT NULL AND {prefix}.longitude IS NOT NULL "
                    f"AND point.distance("
                    f"point({{latitude: {prefix}.latitude, longitude: {prefix}.longitude}}), "
                    "point({latitude: $near_lat, longitude: $near_lng})"
                    ") <= $near_radius_m"
                )
                params["near_lat"] = lat_f
                params["near_lng"] = lng_f
                params["near_radius_m"] = rad_f
        return " AND ".join(parts), params

    def get_cellebrite_events(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
        event_types: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        only_geolocated: bool = False,
        source_apps: Optional[List[str]] = None,
        limit: int = 5000,
        offset: int = 0,
        place: Optional[str] = None,
        near: Optional[Tuple[float, float, float]] = None,
    ) -> dict:
        """
        Unified event feed for the Location & Event Center.
        Returns chronologically-sortable event rows with optional geolocation.
        """
        active = set(event_types) if event_types else {
            "location", "cell_tower", "wifi", "call", "message", "email",
            "power", "device_event", "app_session", "search", "visit", "meeting",
        }

        # Per-type cap: each Cypher returns at most `per_type_cap` newest rows
        # ordered by timestamp DESC. We then merge-sort them and slice to
        # offset+limit. Memory upper bound becomes ~12 x per_type_cap rather
        # than "every matching event in the case" (which previously made
        # this endpoint multi-second on busy cases with no useful indexes).
        # `truncated_types` records which types hit their cap so the response
        # can flag silent truncation honestly per the project rule.
        per_type_cap = max(limit + offset, limit)
        events: list = []
        truncated_types: set = set()
        with self._driver.session() as session:
            # Helper to accumulate results from one cypher and mark the type
            # as truncated when the per-type cap is reached.
            def _add(cypher: str, params: dict, event_type: str, projector):
                rows = list(session.run(cypher, params))
                if len(rows) >= per_type_cap:
                    truncated_types.add(event_type)
                for rec in rows:
                    row = projector(rec)
                    if row:
                        row["event_type"] = event_type
                        events.append(row)

            where, p = self._build_event_filters(
                report_keys, start_date, end_date, source_apps,
                place=place, near=near,
            )
            base_params = {"case_id": case_id, "per_type_cap": per_type_cap, **p}

            # ORDER BY trick: for types where timestamp may be NULL, we want
            # nulls to sort last so they don't crowd out real events when
            # we cap. `n.timestamp IS NULL` is `false (0)` for real values
            # and `true (1)` for nulls, so ascending puts non-null first.
            ts_order = "ORDER BY n.timestamp IS NULL, n.timestamp DESC"

            if "location" in active:
                extra = "" if not only_geolocated else "AND n.latitude IS NOT NULL AND n.longitude IS NOT NULL"
                cypher = f"""
                    MATCH (n:Location {{source_type:'cellebrite'}})
                    WHERE {where} {extra}
                    RETURN n
                    {ts_order}
                    LIMIT $per_type_cap
                """
                _add(cypher, base_params, "location", lambda rec: _project_event(rec["n"], "location"))

            if "cell_tower" in active:
                extra = "" if not only_geolocated else "AND n.latitude IS NOT NULL AND n.longitude IS NOT NULL"
                cypher = f"""
                    MATCH (n:CellTower {{source_type:'cellebrite'}})
                    WHERE {where} {extra}
                    RETURN n
                    {ts_order}
                    LIMIT $per_type_cap
                """
                _add(cypher, base_params, "cell_tower", lambda rec: _project_event(rec["n"], "cell_tower"))

            if "wifi" in active:
                cypher = f"""
                    MATCH (n:WirelessNetwork {{source_type:'cellebrite'}})
                    WHERE {where} AND n.timestamp IS NOT NULL
                    RETURN n
                    ORDER BY n.timestamp DESC
                    LIMIT $per_type_cap
                """
                _add(cypher, base_params, "wifi", lambda rec: _project_event(rec["n"], "wifi"))

            if "call" in active:
                extra = "" if not only_geolocated else \
                    "AND (n.latitude IS NOT NULL OR n.nearest_location_lat IS NOT NULL)"
                cypher = f"""
                    MATCH (n:PhoneCall {{source_type:'cellebrite'}})
                    WHERE {where} {extra}
                    WITH n
                    {ts_order}
                    LIMIT $per_type_cap
                    OPTIONAL MATCH (src:Person)-[:CALLED]->(n)
                    OPTIONAL MATCH (n)-[:CALLED_TO]->(dst:Person)
                    RETURN n, src, dst
                """
                _add(cypher, base_params, "call",
                     lambda rec: _project_call(rec["n"], rec["src"], rec["dst"]))

            if "message" in active:
                extra = "" if not only_geolocated else \
                    "AND (n.latitude IS NOT NULL OR n.nearest_location_lat IS NOT NULL)"
                cypher = f"""
                    MATCH (n:Communication {{source_type:'cellebrite'}})
                    WHERE {where} AND n.body IS NOT NULL {extra}
                    WITH n
                    {ts_order}
                    LIMIT $per_type_cap
                    OPTIONAL MATCH (sender:Person)-[:SENT_MESSAGE]->(n)
                    OPTIONAL MATCH (n)-[:PART_OF]->(chat:Communication)
                    RETURN n, sender, chat
                """
                _add(cypher, base_params, "message",
                     lambda rec: _project_message(rec["n"], rec["sender"], rec["chat"]))

            if "email" in active:
                extra = "" if not only_geolocated else \
                    "AND (n.latitude IS NOT NULL OR n.nearest_location_lat IS NOT NULL)"
                cypher = f"""
                    MATCH (n:Email {{source_type:'cellebrite'}})
                    WHERE {where} {extra}
                    WITH n
                    {ts_order}
                    LIMIT $per_type_cap
                    OPTIONAL MATCH (src:Person)-[:EMAILED]->(n)
                    OPTIONAL MATCH (n)-[:SENT_TO]->(dst:Person)
                    RETURN n, src, dst
                """
                _add(cypher, base_params, "email",
                     lambda rec: _project_email(rec["n"], rec["src"], rec["dst"]))

            if "power" in active or "device_event" in active:
                cypher = f"""
                    MATCH (n:DeviceEvent {{source_type:'cellebrite'}})
                    WHERE {where}
                    RETURN n
                    {ts_order}
                    LIMIT $per_type_cap
                """
                rows = list(session.run(cypher, base_params))
                if len(rows) >= per_type_cap:
                    if "power" in active:
                        truncated_types.add("power")
                    if "device_event" in active:
                        truncated_types.add("device_event")
                for rec in rows:
                    n = dict(rec["n"])
                    etype = "power" if n.get("event_type") == "power" else "device_event"
                    if etype in active:
                        row = _project_event(n, etype)
                        if row:
                            row["event_type"] = etype
                            events.append(row)

            if "app_session" in active:
                cypher = f"""
                    MATCH (n:AppSession {{source_type:'cellebrite'}})
                    WHERE {where}
                    RETURN n
                    {ts_order}
                    LIMIT $per_type_cap
                """
                _add(cypher, base_params, "app_session", lambda rec: _project_event(rec["n"], "app_session"))

            if "search" in active:
                cypher = f"""
                    MATCH (n:SearchedItem {{source_type:'cellebrite'}})
                    WHERE {where} AND n.timestamp IS NOT NULL
                    RETURN n
                    ORDER BY n.timestamp DESC
                    LIMIT $per_type_cap
                """
                _add(cypher, base_params, "search", lambda rec: _project_event(rec["n"], "search"))

            if "visit" in active:
                cypher = f"""
                    MATCH (n:VisitedPage {{source_type:'cellebrite'}})
                    WHERE {where} AND n.timestamp IS NOT NULL
                    RETURN n
                    ORDER BY n.timestamp DESC
                    LIMIT $per_type_cap
                """
                _add(cypher, base_params, "visit", lambda rec: _project_event(rec["n"], "visit"))

            if "meeting" in active:
                # Meetings may not have all filter fields; simpler filter
                rows = list(session.run(
                    "MATCH (n:Meeting {case_id:$case_id}) "
                    "WHERE n.timestamp IS NOT NULL "
                    "RETURN n ORDER BY n.timestamp DESC LIMIT $per_type_cap",
                    case_id=case_id,
                    per_type_cap=per_type_cap,
                ))
                if len(rows) >= per_type_cap:
                    truncated_types.add("meeting")
                for rec in rows:
                    row = _project_event(rec["n"], "meeting")
                    if row:
                        row["event_type"] = "meeting"
                        events.append(row)

        # Sort newest-first so when total > limit the cap drops the oldest
        # events, not the most recent. Events without a timestamp sort to the
        # back - a missing timestamp shouldn't push a real event out of the slice.
        events.sort(
            key=lambda e: (1 if e.get("timestamp") else 0, e.get("timestamp") or ""),
            reverse=True,
        )
        # `total` is now the post-cap count (was the true pre-slice count).
        # The frontend reads `events.length` for display; `truncated` /
        # `truncated_types` is the honest signal that more rows exist.
        total = len(events)
        events = events[offset: offset + limit]
        return {
            "events": events,
            "total": total,
            "truncated": bool(truncated_types),
            "truncated_types": sorted(truncated_types),
            "per_type_cap": per_type_cap,
        }

    def get_cellebrite_event_types(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
    ) -> list:
        """Counts per event type (all + geolocated), powering the filter UI."""
        rk_filter = ""
        params: Dict[str, Any] = {"case_id": case_id}
        if report_keys:
            rk_filter = "AND n.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        out: list = []
        with self._driver.session() as session:
            def _count(label: str, extra_where: str, event_type: str, human: str):
                r = session.run(
                    f"""
                    MATCH (n:{label} {{case_id:$case_id, source_type:'cellebrite'}})
                    WHERE 1=1 {rk_filter} {extra_where}
                    RETURN count(n) AS total,
                           count(CASE WHEN coalesce(n.latitude, n.nearest_location_lat) IS NOT NULL THEN 1 END) AS geo
                    """,
                    params,
                ).single()
                if r and r["total"] > 0:
                    out.append({
                        "event_type": event_type,
                        "label": human,
                        "count": int(r["total"]),
                        "geolocated": int(r["geo"]),
                    })

            _count("Location", "", "location", "Locations / places")
            _count("CellTower", "", "cell_tower", "Cell towers")
            _count("WirelessNetwork", "AND n.timestamp IS NOT NULL", "wifi", "WiFi networks")
            _count("PhoneCall", "", "call", "Calls")
            _count("Communication", "AND n.body IS NOT NULL", "message", "Messages")
            _count("Email", "", "email", "Emails")
            _count("DeviceEvent", "AND n.event_type = 'power'", "power", "Power events")
            _count("DeviceEvent", "AND (n.event_type IS NULL OR n.event_type <> 'power')",
                   "device_event", "Device events")
            _count("AppSession", "", "app_session", "App sessions")
            _count("SearchedItem", "AND n.timestamp IS NOT NULL", "search", "Searches")
            _count("VisitedPage", "AND n.timestamp IS NOT NULL", "visit", "Page visits")

            # Meeting - separate (not always source_type cellebrite)
            r = session.run(
                "MATCH (n:Meeting {case_id:$case_id}) WHERE n.timestamp IS NOT NULL RETURN count(n) AS total",
                case_id=case_id,
            ).single()
            if r and r["total"] > 0:
                out.append({
                    "event_type": "meeting",
                    "label": "Meetings",
                    "count": int(r["total"]),
                    "geolocated": 0,
                })
        return out

    def get_cellebrite_location_tiles(
        self,
        case_id: str,
        zoom: int,
        report_keys: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> dict:
        """
        Tile-aggregated locations for the map at the requested zoom.

        For a case with 100K+ locations, returning every point so the
        frontend can cluster client-side is wasteful - it's ~12 MB JSON
        across the wire when ~5 KB of bucket counts would suffice. This
        endpoint aggregates locations into a quadkey-style lat/lon grid
        whose cell size is set by `zoom`, returning per-tile count and
        top source apps.

        Frontend consumes this for zoom < 15; at higher zoom levels
        the existing /events?event_types=location endpoint returns the
        raw rows (small enough at street-level to render directly).

        bbox: optional (south, west, north, east) - when supplied,
              constrains the aggregation to the visible area; the tile
              cell size is still driven by `zoom` so smooth panning
              gives consistent bucket sizes.
        """
        # Tile resolution: degrees per cell. Each zoom step doubles
        # resolution. zoom=0 approx 22.5 deg per cell (continent-scale chunks);
        # zoom=10 approx 0.022 deg (~2.4 km at the equator).
        # We clamp zoom to [0, 14] - past that, raw points are smaller
        # than tile boundaries, so the caller should switch endpoints.
        z = max(0, min(int(zoom or 0), 14))
        cell_deg = 360.0 / (2 ** (z + 4))  # tuneable; +4 keeps small-z sane

        params: Dict[str, Any] = {
            "case_id": case_id,
            "cell_deg": cell_deg,
        }
        rk_filter = ""
        if report_keys:
            rk_filter = " AND n.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        date_filter = ""
        sd = _normalize_date_bound(start_date)
        ed = _normalize_date_bound(end_date)
        if sd:
            date_filter += " AND coalesce(n.date, n.timestamp, '') >= $start_date"
            params["start_date"] = sd
        if ed:
            date_filter += " AND coalesce(n.date, n.timestamp, '') <= $end_date"
            params["end_date"] = ed

        bbox_filter = ""
        if bbox:
            south, west, north, east = bbox
            bbox_filter = (
                " AND n.latitude >= $bbox_s AND n.latitude <= $bbox_n"
                " AND n.longitude >= $bbox_w AND n.longitude <= $bbox_e"
            )
            params.update({
                "bbox_s": float(south),
                "bbox_n": float(north),
                "bbox_w": float(west),
                "bbox_e": float(east),
            })

        # Bucket via floor(lat / cell) and floor(lon / cell). Returning
        # the bucket index (cell_x, cell_y) plus the bucket centroid lat/
        # lon means the frontend can cluster-render without re-deriving
        # the grid. We collect distinct source apps per bucket so the
        # rail's tile-contents view can preview "WhatsApp + Google Maps
        # +3 more" without a follow-up fetch.
        cypher = f"""
            MATCH (n:Location {{case_id: $case_id, source_type: 'cellebrite'}})
            WHERE n.latitude IS NOT NULL AND n.longitude IS NOT NULL
              {rk_filter}{date_filter}{bbox_filter}
            WITH
              toInteger(floor(n.latitude  / $cell_deg)) AS cy,
              toInteger(floor(n.longitude / $cell_deg)) AS cx,
              n
            RETURN
              cy, cx,
              count(*) AS cnt,
              avg(n.latitude)  AS lat,
              avg(n.longitude) AS lon,
              collect(DISTINCT n.source_app)[..6] AS apps
            ORDER BY cnt DESC
            LIMIT 5000
        """
        tiles: List[dict] = []
        total = 0
        with self._driver.session() as session:
            rs = session.run(cypher, **params)
            for r in rs:
                cnt = int(r["cnt"] or 0)
                total += cnt
                tiles.append({
                    "tile_id": f"{z}-{r['cy']}-{r['cx']}",
                    "cell_x": int(r["cx"]),
                    "cell_y": int(r["cy"]),
                    "lat": r["lat"],
                    "lon": r["lon"],
                    "count": cnt,
                    "top_apps": [a for a in (r["apps"] or []) if a],
                })

        return {
            "zoom": z,
            "cell_deg": cell_deg,
            "tiles": tiles,
            "total": total,
        }

    def get_cellebrite_locations_in_tile(
        self,
        case_id: str,
        cell_x: int,
        cell_y: int,
        cell_deg: float,
        report_keys: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 200,
    ) -> dict:
        """
        Raw locations within a single aggregated tile.

        Powers G3 - the "tile click -> rail with tile contents" path.
        Cheap because the tile bounds collapse the search space to one
        cell of the lat/lon grid.
        """
        if cell_deg <= 0:
            return {"items": [], "total": 0}

        lat_lo = cell_y * cell_deg
        lat_hi = (cell_y + 1) * cell_deg
        lon_lo = cell_x * cell_deg
        lon_hi = (cell_x + 1) * cell_deg

        params: Dict[str, Any] = {
            "case_id": case_id,
            "lat_lo": lat_lo,
            "lat_hi": lat_hi,
            "lon_lo": lon_lo,
            "lon_hi": lon_hi,
            "limit": int(limit),
        }
        rk_filter = ""
        if report_keys:
            rk_filter = " AND n.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        date_filter = ""
        sd = _normalize_date_bound(start_date)
        ed = _normalize_date_bound(end_date)
        if sd:
            date_filter += " AND coalesce(n.date, n.timestamp, '') >= $start_date"
            params["start_date"] = sd
        if ed:
            date_filter += " AND coalesce(n.date, n.timestamp, '') <= $end_date"
            params["end_date"] = ed

        cypher = f"""
            MATCH (n:Location {{case_id: $case_id, source_type: 'cellebrite'}})
            WHERE n.latitude  >= $lat_lo AND n.latitude  < $lat_hi
              AND n.longitude >= $lon_lo AND n.longitude < $lon_hi
              {rk_filter}{date_filter}
            RETURN n
            ORDER BY n.timestamp DESC
            LIMIT $limit
        """
        items = []
        with self._driver.session() as session:
            rs = session.run(cypher, **params)
            for r in rs:
                n = dict(r["n"])
                items.append({
                    "id": n.get("id") or n.get("key"),
                    "node_key": n.get("key"),
                    "label": n.get("name") or "Location",
                    "timestamp": n.get("timestamp"),
                    "latitude": n.get("latitude"),
                    "longitude": n.get("longitude"),
                    "source_app": n.get("source_app"),
                    "location_type": n.get("location_type"),
                    "address": n.get("address"),
                    # Reverse-geocoded fields - see _project_event for
                    # the source-attribution semantics.
                    "place_name": n.get("place_name"),
                    "country": n.get("country"),
                    "country_code": n.get("country_code"),
                    "admin1": n.get("admin1"),
                    "admin2": n.get("admin2"),
                    "geocode_source": n.get("geocode_source"),
                    "geocode_accuracy": n.get("geocode_accuracy"),
                    "accuracy_meters": n.get("accuracy_meters"),
                    "confidence_score": n.get("confidence_score"),
                    "device_report_key": n.get("cellebrite_report_key"),
                })
        return {"items": items, "total": len(items)}

    def get_cellebrite_event_tracks(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        simplify: bool = True,
    ) -> dict:
        """
        Per-device chronologically-ordered location tracks for map polylines.
        Sourced from Location + CellTower + any event with coordinates.
        """
        rk_filter = ""
        params: Dict[str, Any] = {"case_id": case_id}
        if report_keys:
            rk_filter = "AND n.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)
        date_filter = ""
        sd = _normalize_date_bound(start_date)
        ed = _normalize_date_bound(end_date)
        if sd:
            date_filter += " AND coalesce(n.date, n.timestamp, '') >= $start_date"
            params["start_date"] = sd
        if ed:
            date_filter += " AND coalesce(n.date, n.timestamp, '') <= $end_date"
            params["end_date"] = ed

        points_by_device: Dict[str, list] = {}
        with self._driver.session() as session:
            def _collect(cypher: str, source: str):
                r = session.run(cypher, params)
                for rec in r:
                    rk = rec["rk"]
                    if rk is None:
                        continue
                    points_by_device.setdefault(rk, []).append({
                        "timestamp": rec["ts"],
                        "lat": float(rec["lat"]),
                        "lon": float(rec["lon"]),
                        "source": source,
                    })

            _collect(
                f"""
                MATCH (n:Location {{case_id:$case_id, source_type:'cellebrite'}})
                WHERE n.latitude IS NOT NULL AND n.longitude IS NOT NULL
                  AND n.timestamp IS NOT NULL
                  {rk_filter} {date_filter}
                RETURN n.cellebrite_report_key AS rk, n.timestamp AS ts,
                       n.latitude AS lat, n.longitude AS lon
                """,
                "location",
            )
            _collect(
                f"""
                MATCH (n:CellTower {{case_id:$case_id, source_type:'cellebrite'}})
                WHERE n.latitude IS NOT NULL AND n.longitude IS NOT NULL
                  AND n.timestamp IS NOT NULL
                  {rk_filter} {date_filter}
                RETURN n.cellebrite_report_key AS rk, n.timestamp AS ts,
                       n.latitude AS lat, n.longitude AS lon
                """,
                "cell_tower",
            )
            # Also include backfilled nearest_location points from comms so tracks are denser
            for label, src in (("PhoneCall", "call"), ("Communication", "message"), ("Email", "email")):
                body_filter = "AND n.body IS NOT NULL" if label == "Communication" else ""
                _collect(
                    f"""
                    MATCH (n:{label} {{case_id:$case_id, source_type:'cellebrite'}})
                    WHERE coalesce(n.latitude, n.nearest_location_lat) IS NOT NULL
                      AND coalesce(n.longitude, n.nearest_location_lon) IS NOT NULL
                      AND n.timestamp IS NOT NULL
                      {rk_filter} {date_filter} {body_filter}
                    RETURN n.cellebrite_report_key AS rk, n.timestamp AS ts,
                           coalesce(n.latitude, n.nearest_location_lat) AS lat,
                           coalesce(n.longitude, n.nearest_location_lon) AS lon
                    """,
                    f"nearest_{src}",
                )

            # Fetch device metadata (device_model, phone_owner_name, color_hint)
            device_meta: Dict[str, dict] = {}
            r = session.run(
                """
                MATCH (r:PhoneReport {case_id:$case_id})
                OPTIONAL MATCH (r)-[:BELONGS_TO]->(owner:Person)
                RETURN r.key AS key, r.device_model AS model, owner.name AS owner
                """,
                case_id=case_id,
            )
            palette = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2", "#db2777"]
            for i, rec in enumerate(r):
                k = rec["key"]
                if k:
                    device_meta[k] = {
                        "device_model": rec["model"] or "Device",
                        "phone_owner_name": rec["owner"] or "",
                        "color_hint": palette[i % len(palette)],
                    }

        # Sort each device's points chronologically + optional simplify
        tracks = []
        for rk, pts in points_by_device.items():
            pts.sort(key=lambda p: p["timestamp"] or "")
            if simplify:
                pts = _simplify_points(pts, min_dist_m=50, min_time_s=60)
            meta = device_meta.get(rk, {"device_model": "Device", "phone_owner_name": "", "color_hint": "#2563eb"})
            tracks.append({
                "device_report_key": rk,
                "device_model": meta["device_model"],
                "phone_owner_name": meta["phone_owner_name"],
                "color_hint": meta["color_hint"],
                "points": pts,
            })

        return {"tracks": tracks}

    def get_cellebrite_event_detail(self, case_id: str, node_key: str) -> Optional[dict]:
        """
        Fetch one event's full properties for the detail drawer.

        For comms-typed events (PhoneCall, Email, Communication aka
        message), this also OPTIONAL MATCHes the sender + recipient
        Person nodes so the drawer doesn't have to depend on the caller
        passing pre-resolved party data. Without this the drawer
        rendered "Unknown -> Unknown" because the projection used to
        return only `properties(n)`.
        """
        # Per-label query templates. Each returns the node properties
        # plus structured `sender` / `recipient` / `recipients` dicts
        # where the relationship pattern dictates.
        comms_queries = {
            "PhoneCall": """
                MATCH (n:PhoneCall {case_id:$case_id, key:$key})
                OPTIONAL MATCH (src:Person)-[:CALLED]->(n)
                OPTIONAL MATCH (n)-[:CALLED_TO]->(dst:Person)
                RETURN properties(n) AS p,
                       properties(src) AS sender,
                       properties(dst) AS recipient
                LIMIT 1
            """,
            "Email": """
                MATCH (n:Email {case_id:$case_id, key:$key})
                OPTIONAL MATCH (src:Person)-[:EMAILED]->(n)
                OPTIONAL MATCH (n)-[:SENT_TO]->(dst:Person)
                WITH n, properties(n) AS p, properties(src) AS sender,
                     collect(DISTINCT properties(dst)) AS rcpts
                RETURN p, sender,
                       (CASE WHEN size(rcpts) > 0 THEN rcpts[0] ELSE null END) AS recipient,
                       rcpts AS recipients
                LIMIT 1
            """,
            "Communication": """
                MATCH (n:Communication {case_id:$case_id, key:$key})
                OPTIONAL MATCH (src:Person)-[:SENT_MESSAGE]->(n)
                OPTIONAL MATCH (n)-[:PART_OF]->(parent:Communication)
                OPTIONAL MATCH (other:Person)-[:PARTICIPATED_IN]->(parent)
                  WHERE other <> src OR src IS NULL
                WITH n, properties(n) AS p, properties(src) AS sender,
                     collect(DISTINCT properties(other)) AS rcpts
                RETURN p, sender,
                       (CASE WHEN size(rcpts) > 0 THEN rcpts[0] ELSE null END) AS recipient,
                       rcpts AS recipients
                LIMIT 1
            """,
        }
        plain_labels = (
            "Location", "CellTower", "WirelessNetwork", "DeviceEvent",
            "AppSession", "SearchedItem", "VisitedPage", "Meeting",
        )
        with self._driver.session() as session:
            # Comms-bearing labels first - these need party resolution.
            for label, query in comms_queries.items():
                r = session.run(query, case_id=case_id, key=node_key).single()
                if not r:
                    continue
                props = dict(r["p"])
                props["_label"] = label

                def _person(p):
                    if not p:
                        return None
                    party = dict(p)
                    return {
                        "key": party.get("key"),
                        "name": party.get("name") or party.get("key"),
                        "is_owner": bool(party.get("is_phone_owner")),
                    }

                props["sender"] = _person(r.get("sender"))
                props["recipient"] = _person(r.get("recipient"))
                if "recipients" in r.keys():
                    props["recipients"] = [_person(p) for p in (r.get("recipients") or []) if p]
                return props

            # Plain (non-comms) labels - original behaviour.
            for label in plain_labels:
                r = session.run(
                    f"MATCH (n:{label} {{case_id:$case_id, key:$key}}) RETURN properties(n) AS p LIMIT 1",
                    case_id=case_id, key=node_key,
                ).single()
                if r:
                    props = dict(r["p"])
                    props["_label"] = label
                    return props
        return None

    def get_event_related(
        self,
        case_id: str,
        node_key: str,
        window_h: int = 24,
        limit: int = 50,
    ) -> dict:
        """
        Return events related to a clicked comms event, in two buckets:

            {
                "thread":  [event-rows],   # surrounding messages in the same conversation
                "around":  [event-rows],   # cross-channel pair window (+/-window_h hours)
                "anchor":  { "node_key": ..., "label": ..., "timestamp": ... }
            }

        - **thread**: only populated for messages that have a parent
          Communication thread; ordered chronologically; capped at `limit`
          rows centred on the anchor.
        - **around**: comms (calls/messages/emails) involving the SAME
          party pair as the anchor, within +/-window_h hours of the anchor's
          timestamp. Self-comms (sender == recipient) are excluded.

        Cheap by design - no full-text fan-out, just per-relationship
        keyset filters on (case_id, time, party_keys). Returns empty
        buckets gracefully when the anchor is a non-comms node (e.g.
        Location, CellTower) - the rail just shows the existing detail.
        """
        # Find the anchor's label + party keys + timestamp + thread_id (if any)
        # in one shot. The detail-fetch already does most of this; we redo it
        # here in a leaner shape so the rail can fire this in parallel with
        # the detail call without serialising the two.
        anchor_query = """
            MATCH (n {case_id:$case_id, key:$key})
            WHERE n:PhoneCall OR n:Email OR n:Communication
            OPTIONAL MATCH (src:Person)-[r1:CALLED|EMAILED|SENT_MESSAGE]->(n)
            OPTIONAL MATCH (n)-[r2:CALLED_TO|SENT_TO]->(dst:Person)
            OPTIONAL MATCH (n)-[:PART_OF]->(parent:Communication)
            OPTIONAL MATCH (other:Person)-[:PARTICIPATED_IN]->(parent)
              WHERE other <> src OR src IS NULL
            WITH n, src, dst, parent,
                 collect(DISTINCT other.key) AS thread_party_keys
            RETURN labels(n) AS labels,
                   n.key AS key,
                   n.timestamp AS timestamp,
                   n.date AS date,
                   n.time AS time,
                   src.key AS sender_key,
                   src.name AS sender_name,
                   dst.key AS recipient_key,
                   dst.name AS recipient_name,
                   parent.key AS thread_key,
                   thread_party_keys
            LIMIT 1
        """
        with self._driver.session() as session:
            r = session.run(anchor_query, case_id=case_id, key=node_key).single()
            if not r:
                return {"thread": [], "around": [], "anchor": None}

            anchor_label = next(
                (l for l in (r["labels"] or []) if l in ("PhoneCall", "Email", "Communication")),
                None,
            )
            sender_key = r["sender_key"]
            recipient_key = r["recipient_key"]
            thread_key = r["thread_key"]
            thread_parties: List[str] = list(r["thread_party_keys"] or [])
            anchor_ts = r["timestamp"]
            anchor_date = r["date"]
            anchor_time = r["time"]

            # The pair set used for the cross-channel window. For
            # messages this includes thread participants too so a
            # group-chat anchor pulls in the calls/emails between
            # those same people, not just the direct sender->recipient
            # pair which often doesn't exist on group messages.
            pair_keys = [k for k in {sender_key, recipient_key, *thread_parties} if k]

            anchor_dict = {
                "node_key": r["key"],
                "label": anchor_label or "Event",
                "timestamp": anchor_ts,
                "date": anchor_date,
                "time": anchor_time,
                "sender": {"key": sender_key, "name": r["sender_name"]} if sender_key else None,
                "recipient": {"key": recipient_key, "name": r["recipient_name"]} if recipient_key else None,
                "thread_key": thread_key,
            }

            thread_rows: List[dict] = []
            around_rows: List[dict] = []

            # ----------------- Thread branch -----------------
            # Only meaningful for messages with a parent thread node.
            # Returns siblings ordered chronologically; the UI can scroll
            # within the cap. We don't centre-on-anchor here (would need
            # a second window query); the cap is generous enough that
            # the anchor is almost always present in the slice.
            if anchor_label == "Communication" and thread_key:
                thread_q = """
                    MATCH (parent:Communication {case_id:$case_id, key:$thread_key})
                    MATCH (sib:Communication)-[:PART_OF]->(parent)
                    OPTIONAL MATCH (sender:Person)-[:SENT_MESSAGE]->(sib)
                    RETURN sib AS n, sender AS sender, parent AS chat
                    ORDER BY coalesce(sib.timestamp, sib.date) ASC
                    LIMIT $limit
                """
                for row in session.run(
                    thread_q,
                    case_id=case_id,
                    thread_key=thread_key,
                    limit=int(limit),
                ):
                    proj = _project_message(row["n"], row.get("sender"), row.get("chat"))
                    if proj:
                        thread_rows.append(proj)

            # ----------------- Around branch -----------------
            # Cross-channel: any PhoneCall / Email / Communication where
            # both the sender and at-least-one recipient are in the pair
            # set, within +/-window_h of the anchor's timestamp. Sorted by
            # absolute time-distance from the anchor so the closest
            # events surface first regardless of direction.
            if pair_keys and (anchor_ts or anchor_date):
                # Compute the window in plain ISO date for the date-only
                # filter, and an extra timestamp filter when anchor_ts
                # is present. This dual approach handles both the rich
                # timestamp case and the date-only case (Cellebrite
                # sometimes carries one but not both).
                from datetime import datetime, timedelta
                ref = None
                if anchor_ts:
                    try:
                        ref = datetime.fromisoformat(anchor_ts.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        ref = None
                if ref is None and anchor_date:
                    try:
                        ref = datetime.fromisoformat(anchor_date)
                    except (ValueError, AttributeError):
                        ref = None
                if ref is not None:
                    lo = (ref - timedelta(hours=window_h)).isoformat()
                    hi = (ref + timedelta(hours=window_h)).isoformat()
                    lo_d = (ref - timedelta(hours=window_h)).date().isoformat()
                    hi_d = (ref + timedelta(hours=window_h)).date().isoformat()
                    around_q = """
                        // Calls
                        MATCH (c:PhoneCall {case_id:$case_id})
                        WHERE coalesce(c.timestamp, c.date) >= $lo_d
                          AND coalesce(c.timestamp, c.date) <= $hi_d
                          AND c.key <> $anchor_key
                        OPTIONAL MATCH (cs:Person)-[:CALLED]->(c)
                        OPTIONAL MATCH (c)-[:CALLED_TO]->(cd:Person)
                        WITH c, cs, cd
                        WHERE (cs IS NOT NULL AND cs.key IN $pair_keys)
                           OR (cd IS NOT NULL AND cd.key IN $pair_keys)
                        RETURN 'call' AS kind, c AS n, cs AS src, cd AS dst, NULL AS chat
                        UNION ALL
                        // Messages
                        MATCH (m:Communication {case_id:$case_id})
                        WHERE coalesce(m.timestamp, m.date) >= $lo_d
                          AND coalesce(m.timestamp, m.date) <= $hi_d
                          AND m.key <> $anchor_key
                        OPTIONAL MATCH (ms:Person)-[:SENT_MESSAGE]->(m)
                        OPTIONAL MATCH (m)-[:PART_OF]->(mt:Communication)
                        OPTIONAL MATCH (mp:Person)-[:PARTICIPATED_IN]->(mt)
                        WITH m, ms, mt, collect(DISTINCT mp.key) AS mt_keys
                        WHERE (ms IS NOT NULL AND ms.key IN $pair_keys)
                           OR any(k IN mt_keys WHERE k IN $pair_keys)
                        RETURN 'message' AS kind, m AS n, ms AS src, NULL AS dst, mt AS chat
                        UNION ALL
                        // Emails
                        MATCH (e:Email {case_id:$case_id})
                        WHERE coalesce(e.timestamp, e.date) >= $lo_d
                          AND coalesce(e.timestamp, e.date) <= $hi_d
                          AND e.key <> $anchor_key
                        OPTIONAL MATCH (es:Person)-[:EMAILED]->(e)
                        OPTIONAL MATCH (e)-[:SENT_TO]->(ed:Person)
                        WITH e, es, ed
                        WHERE (es IS NOT NULL AND es.key IN $pair_keys)
                           OR (ed IS NOT NULL AND ed.key IN $pair_keys)
                        RETURN 'email' AS kind, e AS n, es AS src, ed AS dst, NULL AS chat
                    """
                    for row in session.run(
                        around_q,
                        case_id=case_id,
                        lo_d=lo_d, hi_d=hi_d,
                        anchor_key=node_key,
                        pair_keys=pair_keys,
                    ):
                        kind = row["kind"]
                        if kind == "call":
                            proj = _project_call(row["n"], row.get("src"), row.get("dst"))
                        elif kind == "message":
                            proj = _project_message(row["n"], row.get("src"), row.get("chat"))
                        else:  # email
                            proj = _project_event(row["n"], "email")
                        if proj:
                            around_rows.append(proj)

                    # Sort by distance from the anchor's timestamp.
                    def _dist(r):
                        ts = r.get("timestamp")
                        if not ts:
                            return float("inf")
                        try:
                            return abs((datetime.fromisoformat(ts.replace("Z", "+00:00")) - ref).total_seconds())
                        except (ValueError, AttributeError):
                            return float("inf")
                    around_rows.sort(key=_dist)
                    if len(around_rows) > limit:
                        around_rows = around_rows[:limit]

            return {
                "anchor": anchor_dict,
                "thread": thread_rows,
                "around": around_rows,
            }

    def get_overview_contacts(
        self,
        case_id: str,
        report_key: str,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        """All Person nodes from one device, with interaction counts."""
        params: Dict[str, Any] = {
            "case_id": case_id,
            "rk": report_key,
            "limit": int(limit),
            "offset": int(offset),
        }
        search_clause = ""
        if search:
            search_clause = (
                " AND (toLower(coalesce(p.name, '')) CONTAINS toLower($search) "
                "OR any(num IN coalesce(p.phone_numbers, []) WHERE toLower(num) CONTAINS toLower($search)))"
            )
            params["search"] = search

        with self._driver.session() as session:
            total = session.run(
                f"""
                MATCH (p:Person {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE p.key IS NOT NULL {search_clause}
                RETURN count(p) AS n
                """,
                params,
            ).single()
            total_count = int(total["n"]) if total else 0

            result = session.run(
                f"""
                MATCH (p:Person {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE p.key IS NOT NULL {search_clause}
                OPTIONAL MATCH (p)-[r1:CALLED|CALLED_TO]-(c:PhoneCall)
                WITH p, count(DISTINCT c) AS calls
                OPTIONAL MATCH (p)-[r2:SENT_MESSAGE]-(m:Communication)
                WITH p, calls, count(DISTINCT m) AS msgs_out
                OPTIONAL MATCH (p)-[:PARTICIPATED_IN]->(chat:Communication)
                OPTIONAL MATCH (msg:Communication)-[:PART_OF]->(chat)
                WHERE msg.body IS NOT NULL
                WITH p, calls, msgs_out, count(DISTINCT msg) AS msgs_chat
                OPTIONAL MATCH (p)-[:EMAILED|SENT_TO]-(e:Email)
                WITH p, calls, msgs_out, msgs_chat, count(DISTINCT e) AS emails
                RETURN p.key AS key,
                       p.name AS name,
                       p.phone_numbers AS phone_numbers,
                       p.is_phone_owner AS is_phone_owner,
                       p.cellebrite_id AS cellebrite_id,
                       p.all_identifiers AS all_identifiers,
                       calls,
                       msgs_out + msgs_chat AS messages,
                       emails,
                       calls + msgs_out + msgs_chat + emails AS interactions
                ORDER BY interactions DESC, name
                SKIP $offset LIMIT $limit
                """,
                params,
            )
            rows = []
            for rec in result:
                rows.append({
                    "key": rec["key"],
                    "name": rec["name"] or rec["key"],
                    "phone_numbers": list(rec["phone_numbers"] or []),
                    "is_phone_owner": bool(rec["is_phone_owner"]),
                    "cellebrite_id": rec["cellebrite_id"],
                    "all_identifiers": list(rec["all_identifiers"] or []),
                    "calls": int(rec["calls"] or 0),
                    "messages": int(rec["messages"] or 0),
                    "emails": int(rec["emails"] or 0),
                    "interactions": int(rec["interactions"] or 0),
                })
            return {"rows": rows, "total": total_count}

    def get_unified_contacts(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        """
        Roll up Person nodes by canonical (E.164-normalised) phone number
        so investigators can see "who across all phones is +12028052817"
        in one row, with the alias names each device used.

        Persons whose `phone_numbers` can't be normalised (alphanumeric
        senders, app IDs, short codes) are kept under their raw key as a
        single-alias row - they're not lost from the rollup, they just
        don't merge with anyone else.

        Returns:
            {
                "rows": [
                    {
                        "canonical": "+12028052817" | null,
                        "display_number": "+1 (202) 805-2817" | null,
                        "aliases": [
                            {"name": "Alex", "key": "phone-...",
                             "report_keys": ["..."]},
                            ...                       # most-used name first
                        ],
                        "report_keys": [...],         # union across aliases
                        "person_keys": [...],         # union (for filter wiring)
                        "is_phone_owner": bool,       # any alias is owner
                        "msg_count": N,
                        "call_count": N,
                        "email_count": N,
                        "first_seen": "ISO" | null,
                        "last_seen":  "ISO" | null,
                        "interactions": N             # sum of the three
                    },
                    ...                               # ordered by interactions desc
                ],
                "total": N                            # rows BEFORE limit/offset
            }

        `report_keys`, when provided, restricts BOTH the Person filter
        and the count MATCHes - so the rollup reflects "what these
        selected phones see" rather than the case-wide picture.
        """
        # Local import: keeps the cellebrite-only normaliser out of
        # neo4j_service's top-of-file dep set. Cheap (no I/O).
        from services.phone_normalise import (
            normalise,
            normalise_all,
            normalise_from_person_key,
            display_format,
        )

        # Hard cap on the Person fanout - no real investigation has 10K+
        # unique humans in their contacts. The cap is a safety rail so a
        # malformed case (or a phantom 100K-Person case) can't wedge
        # the backend like the unbounded version did. If we ever hit
        # this limit in real data, surface a "truncated" hint in the
        # UI rather than uncapping silently.
        PERSON_CAP = 5000
        # Cap aliases per bucket so a really busy number (like a
        # delivery service that 50 phones all named differently) doesn't
        # blow out the response payload.
        ALIASES_PER_BUCKET = 30

        params: Dict[str, Any] = {
            "case_id": case_id,
            "person_cap": PERSON_CAP,
        }
        rk_clause = ""
        if report_keys:
            rk_clause = " AND p.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        # Single Cypher pass: pull every Person AND their per-person
        # event counts + min/max timestamps in one round-trip. We do
        # the canonical-number bucketing in Python (the regex
        # normaliser doesn't translate cleanly to Cypher and the
        # bucketing math is dict ops on at-most-5000 rows, microseconds
        # of work). The previous version did 3 Cypher queries PER
        # BUCKET - at hundreds of buckets that was thousands of
        # serial round-trips, which wedged the Neo4j connection pool
        # and killed the backend on OPDMD28-scale cases.
        with self._driver.session() as session:
            persons = list(session.run(
                f"""
                MATCH (p:Person {{case_id:$case_id, source_type:'cellebrite'}})
                WHERE p.key IS NOT NULL {rk_clause}
                CALL {{
                    WITH p
                    OPTIONAL MATCH (p)-[:CALLED|CALLED_TO]-(c:PhoneCall {{case_id:$case_id}})
                    RETURN count(DISTINCT c) AS calls,
                           min(c.timestamp) AS calls_lo,
                           max(c.timestamp) AS calls_hi
                }}
                CALL {{
                    WITH p
                    OPTIONAL MATCH (p)-[:SENT_MESSAGE]-(m:Communication {{case_id:$case_id}})
                    RETURN count(DISTINCT m) AS msgs,
                           min(m.timestamp) AS msgs_lo,
                           max(m.timestamp) AS msgs_hi
                }}
                CALL {{
                    WITH p
                    OPTIONAL MATCH (p)-[:EMAILED|SENT_TO]-(e:Email {{case_id:$case_id}})
                    RETURN count(DISTINCT e) AS emails,
                           min(e.timestamp) AS emails_lo,
                           max(e.timestamp) AS emails_hi
                }}
                RETURN p.key AS key,
                       p.name AS name,
                       p.phone_numbers AS phone_numbers,
                       p.cellebrite_report_key AS report_key,
                       coalesce(p.is_phone_owner, false) AS is_phone_owner,
                       calls, calls_lo, calls_hi,
                       msgs, msgs_lo, msgs_hi,
                       emails, emails_lo, emails_hi
                ORDER BY (calls + msgs + emails) DESC
                LIMIT $person_cap
                """,
                params,
            ))

            person_count = len(persons)
            truncated = person_count >= PERSON_CAP

            # Bucket by canonical number(s) - a single Person joins
            # EVERY canonical bucket their data points at, not just the
            # first. This is the unification logic that makes the
            # rollup actually unify: a Person with phones
            # ["12407063672", "5892435332"] joins both +12407063672
            # AND +15892435332 buckets, so any other Person carrying
            # either number ends up grouped with them.
            #
            # Sources of canonical candidates per Person, in priority
            # order:
            #   1. Every string in `phone_numbers` (most explicit)
            #   2. The Person's `name` if it looks like a number
            #      (Cellebrite stores unsaved-contact callers this way)
            #   3. The `phone-{digits}` person key itself (last-resort
            #      signal - Cellebrite minted the key from the number)
            #
            # When NO source produces a canonical, the Person sits
            # alone under a synthetic `raw:{key}` bucket so they're
            # not lost from the table.
            buckets: Dict[str, dict] = {}

            def _ensure_bucket(bk, canonical):
                b = buckets.get(bk)
                if b is None:
                    b = {
                        "canonical": canonical,
                        "display_number": display_format(canonical),
                        # Per-alias dict keyed by (name, person_key) so
                        # the same name on different phones shows up
                        # once per phone (the report_keys list captures
                        # that).
                        "_alias_map": {},
                        "person_keys": set(),
                        "report_keys": set(),
                        "is_phone_owner": False,
                        "call_count": 0,
                        "msg_count": 0,
                        "email_count": 0,
                        "_lo": None,
                        "_hi": None,
                    }
                    buckets[bk] = b
                return b

            for rec in persons:
                key = rec["key"]
                name = rec["name"] or key
                rk = rec["report_key"]
                phones = list(rec["phone_numbers"] or [])

                # Gather every canonical candidate for this Person.
                # Order matters for the de-dup but not for joining -
                # we add the Person to every distinct canonical bucket.
                candidates = list(normalise_all(phones))
                # Name fallback - if no phone strings normalised AND
                # the name looks like a number, accept it. Common for
                # unsaved-contact rows where Cellebrite uses the raw
                # number as the display name.
                if not candidates:
                    name_canon = normalise(name)
                    if name_canon:
                        candidates.append(name_canon)
                # Person-key fallback - Cellebrite mints the key as
                # `phone-{digits}` so it's a strong signal even when
                # the rest of the data is junk. Only adds if not
                # already covered by phones / name.
                key_canon = normalise_from_person_key(key)
                if key_canon and key_canon not in candidates:
                    candidates.append(key_canon)

                # Deduplicate across the sources.
                candidates = list(dict.fromkeys(candidates))

                if not candidates:
                    # No canonical at all - Person sits alone under a
                    # synthetic key so they still appear in the table.
                    target_buckets = [_ensure_bucket(f"raw:{key}", None)]
                else:
                    target_buckets = [_ensure_bucket(c, c) for c in candidates]

                for b in target_buckets:
                    b["person_keys"].add(key)
                    if rk:
                        b["report_keys"].add(rk)
                    if rec["is_phone_owner"]:
                        b["is_phone_owner"] = True

                    # Counts: sum across aliases. NB the per-Person
                    # counts came back via per-Person OPTIONAL MATCH so
                    # a message that names two aliases in the same
                    # bucket WILL be counted twice. For the rollup
                    # display this is the less-bad failure - slightly
                    # inflates very-active contacts; the alternative
                    # (subquery on the union of keys) was the N+1 query
                    # that wedged the backend.
                    #
                    # When a Person joins multiple canonical buckets
                    # the per-Person counts are added to EACH bucket -
                    # also a slight inflation, but the alternative
                    # (splitting comms per number) requires per-event
                    # number resolution we don't have.
                    b["call_count"] += int(rec["calls"] or 0)
                    b["msg_count"] += int(rec["msgs"] or 0)
                    b["email_count"] += int(rec["emails"] or 0)

                    # Min/max across the bucket - pull only non-null
                    # values since an alias with zero of a given event
                    # type contributes nulls.
                    for lo_v in (rec["calls_lo"], rec["msgs_lo"], rec["emails_lo"]):
                        if lo_v and (b["_lo"] is None or lo_v < b["_lo"]):
                            b["_lo"] = lo_v
                    for hi_v in (rec["calls_hi"], rec["msgs_hi"], rec["emails_hi"]):
                        if hi_v and (b["_hi"] is None or hi_v > b["_hi"]):
                            b["_hi"] = hi_v

                    alias_key = (name, key)
                    alias = b["_alias_map"].get(alias_key)
                    if alias is None:
                        alias = {"name": name, "key": key, "report_keys": set()}
                        b["_alias_map"][alias_key] = alias
                    if rk:
                        alias["report_keys"].add(rk)

            # Apply optional search filter on number OR alias name.
            if search:
                needle = search.lower()
                buckets = {
                    k: b for k, b in buckets.items()
                    if (b["canonical"] and needle in b["canonical"])
                    or (b["display_number"] and needle in b["display_number"].lower())
                    or any(needle in a["name"].lower() for a in b["_alias_map"].values())
                }

            # Materialise first/last seen from the per-bucket min/max
            # we accumulated above. Names changed for the response
            # contract.
            for b in buckets.values():
                b["first_seen"] = b.pop("_lo", None)
                b["last_seen"] = b.pop("_hi", None)

            # Materialise rows. Aliases sorted by best-effort frequency
            # proxy (number of report_keys they appear on, then name).
            # Capped at ALIASES_PER_BUCKET to keep the payload bounded
            # for pathological cases (e.g. a courier number in 50
            # phones' contact lists).
            rows = []
            for b in buckets.values():
                all_aliases = sorted(
                    b["_alias_map"].values(),
                    key=lambda a: (-len(a["report_keys"]), a["name"]),
                )
                aliases = all_aliases[:ALIASES_PER_BUCKET]
                aliases_truncated_by = max(0, len(all_aliases) - ALIASES_PER_BUCKET)
                # Convert sets -> lists for JSON serialisation.
                for a in aliases:
                    a["report_keys"] = sorted(a["report_keys"])
                interactions = (
                    b["msg_count"] + b["call_count"] + b["email_count"]
                )
                rows.append({
                    "canonical": b["canonical"],
                    "display_number": b["display_number"],
                    "aliases": aliases,
                    "aliases_truncated_by": aliases_truncated_by,
                    "person_keys": sorted(b["person_keys"]),
                    "report_keys": sorted(b["report_keys"]),
                    "is_phone_owner": b["is_phone_owner"],
                    "msg_count": b["msg_count"],
                    "call_count": b["call_count"],
                    "email_count": b["email_count"],
                    "first_seen": b["first_seen"],
                    "last_seen": b["last_seen"],
                    "interactions": interactions,
                })

            # Sort: phone-owner aliases first (the case's own users),
            # then by interaction volume desc, then by display number.
            rows.sort(
                key=lambda r: (
                    not r["is_phone_owner"],
                    -r["interactions"],
                    r["display_number"] or "zzz",
                )
            )
            total = len(rows)
            return {
                "rows": rows[offset : offset + limit],
                "total": total,
                # If true, the upstream Person fetch hit PERSON_CAP and
                # the rollup is incomplete - callers should surface
                # this to the user so they don't wonder why a number
                # they expect isn't in the list.
                "truncated": truncated,
                "person_count": person_count,
                "person_cap": PERSON_CAP,
            }

    def get_overview_calls(
        self,
        case_id: str,
        report_key: str,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        """All PhoneCalls from one device with parties resolved."""
        params: Dict[str, Any] = {
            "case_id": case_id,
            "rk": report_key,
            "limit": int(limit),
            "offset": int(offset),
        }
        search_clause = ""
        if search:
            search_clause = (
                " AND (toLower(coalesce(c.source_app, '')) CONTAINS toLower($search) "
                "OR toLower(coalesce(c.direction, '')) CONTAINS toLower($search))"
            )
            params["search"] = search

        with self._driver.session() as session:
            total = session.run(
                f"""
                MATCH (c:PhoneCall {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE 1=1 {search_clause}
                RETURN count(c) AS n
                """,
                params,
            ).single()
            total_count = int(total["n"]) if total else 0

            result = session.run(
                f"""
                MATCH (c:PhoneCall {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE 1=1 {search_clause}
                OPTIONAL MATCH (src:Person)-[:CALLED]->(c)
                OPTIONAL MATCH (c)-[:CALLED_TO]->(dst:Person)
                RETURN c, src, dst
                ORDER BY c.timestamp DESC
                SKIP $offset LIMIT $limit
                """,
                params,
            )
            rows = []
            for rec in result:
                c = dict(rec["c"])
                src = dict(rec["src"]) if rec["src"] else None
                dst = dict(rec["dst"]) if rec["dst"] else None
                rows.append({
                    "key": c.get("key"),
                    "id": c.get("id"),
                    "node_key": c.get("key"),
                    "timestamp": c.get("timestamp"),
                    "date": c.get("date"),
                    "time": c.get("time"),
                    "direction": c.get("direction"),
                    "call_type": c.get("call_type"),
                    "duration": c.get("duration"),
                    "video_call": bool(c.get("video_call")),
                    "source_app": c.get("source_app"),
                    "deleted_state": c.get("deleted_state"),
                    "from_name": (src.get("name") if src else None),
                    "from_key": (src.get("key") if src else None),
                    "to_name": (dst.get("name") if dst else None),
                    "to_key": (dst.get("key") if dst else None),
                })
            return {"rows": rows, "total": total_count}

    def get_overview_messages(
        self,
        case_id: str,
        report_key: str,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        """All individual messages (Communication with body) from one device."""
        params: Dict[str, Any] = {
            "case_id": case_id,
            "rk": report_key,
            "limit": int(limit),
            "offset": int(offset),
        }
        search_clause = ""
        if search:
            search_clause = " AND toLower(coalesce(m.body, '')) CONTAINS toLower($search)"
            params["search"] = search

        with self._driver.session() as session:
            total = session.run(
                f"""
                MATCH (m:Communication {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE m.body IS NOT NULL {search_clause}
                RETURN count(m) AS n
                """,
                params,
            ).single()
            total_count = int(total["n"]) if total else 0

            result = session.run(
                f"""
                MATCH (m:Communication {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE m.body IS NOT NULL {search_clause}
                OPTIONAL MATCH (sender:Person)-[:SENT_MESSAGE]->(m)
                OPTIONAL MATCH (m)-[:PART_OF]->(chat:Communication)
                RETURN m, sender, chat
                ORDER BY m.timestamp DESC
                SKIP $offset LIMIT $limit
                """,
                params,
            )
            rows = []
            for rec in result:
                m = dict(rec["m"])
                sender = dict(rec["sender"]) if rec["sender"] else None
                chat = dict(rec["chat"]) if rec["chat"] else None
                body = m.get("body") or ""
                rows.append({
                    "key": m.get("key"),
                    "id": m.get("id"),
                    "node_key": m.get("key"),
                    "timestamp": m.get("timestamp"),
                    "date": m.get("date"),
                    "time": m.get("time"),
                    "source_app": m.get("source_app"),
                    "message_type": m.get("message_type"),
                    "body": body,
                    "body_preview": body[:160],
                    "deleted_state": m.get("deleted_state"),
                    "attachment_count": int(m.get("attachment_count") or 0),
                    "sender_name": (sender.get("name") if sender else None),
                    "sender_key": (sender.get("key") if sender else None),
                    "thread_id": (chat.get("key") if chat else None),
                    "thread_name": (chat.get("name") if chat else None),
                })
            return {"rows": rows, "total": total_count}

    def get_overview_locations(
        self,
        case_id: str,
        report_key: str,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        """All Locations from one device."""
        params: Dict[str, Any] = {
            "case_id": case_id,
            "rk": report_key,
            "limit": int(limit),
            "offset": int(offset),
        }
        search_clause = ""
        if search:
            search_clause = (
                " AND (toLower(coalesce(l.name, '')) CONTAINS toLower($search) "
                "OR toLower(coalesce(l.location_type, '')) CONTAINS toLower($search) "
                "OR toLower(coalesce(l.source_app, '')) CONTAINS toLower($search))"
            )
            params["search"] = search

        with self._driver.session() as session:
            total = session.run(
                f"""
                MATCH (l:Location {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE 1=1 {search_clause}
                RETURN count(l) AS n
                """,
                params,
            ).single()
            total_count = int(total["n"]) if total else 0

            result = session.run(
                f"""
                MATCH (l:Location {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE 1=1 {search_clause}
                RETURN l
                ORDER BY coalesce(l.timestamp, '') DESC
                SKIP $offset LIMIT $limit
                """,
                params,
            )
            rows = []
            for rec in result:
                l = dict(rec["l"])
                rows.append({
                    "key": l.get("key"),
                    "id": l.get("id"),
                    "node_key": l.get("key"),
                    "name": l.get("name"),
                    "location_type": l.get("location_type"),
                    "source_app": l.get("source_app"),
                    "latitude": l.get("latitude"),
                    "longitude": l.get("longitude"),
                    "timestamp": l.get("timestamp"),
                    "date": l.get("date"),
                    "time": l.get("time"),
                    "deleted_state": l.get("deleted_state"),
                })
            return {"rows": rows, "total": total_count}

    def get_overview_emails(
        self,
        case_id: str,
        report_key: str,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        """All Emails from one device with sender + first recipient resolved."""
        params: Dict[str, Any] = {
            "case_id": case_id,
            "rk": report_key,
            "limit": int(limit),
            "offset": int(offset),
        }
        search_clause = ""
        if search:
            search_clause = (
                " AND (toLower(coalesce(e.subject, '')) CONTAINS toLower($search) "
                "OR toLower(coalesce(e.body, '')) CONTAINS toLower($search) "
                "OR toLower(coalesce(e.folder, '')) CONTAINS toLower($search))"
            )
            params["search"] = search

        with self._driver.session() as session:
            total = session.run(
                f"""
                MATCH (e:Email {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE 1=1 {search_clause}
                RETURN count(e) AS n
                """,
                params,
            ).single()
            total_count = int(total["n"]) if total else 0

            result = session.run(
                f"""
                MATCH (e:Email {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE 1=1 {search_clause}
                OPTIONAL MATCH (src:Person)-[:EMAILED]->(e)
                OPTIONAL MATCH (e)-[:SENT_TO]->(dst:Person)
                WITH e, src, collect(DISTINCT dst) AS dsts
                RETURN e, src, dsts
                ORDER BY e.timestamp DESC
                SKIP $offset LIMIT $limit
                """,
                params,
            )
            rows = []
            for rec in result:
                e = dict(rec["e"])
                src = dict(rec["src"]) if rec["src"] else None
                dsts = [dict(d) for d in rec["dsts"] if d is not None]
                first_dst = dsts[0] if dsts else None

                # Synthesise a per-pair thread_id matching the format used
                # in get_threads/get_thread_detail for emails:
                #   emails-{report_key}-{sorted_keyA}-{sorted_keyB}
                # This lets the UI ask the existing thread-detail endpoint
                # for the whole "everything between these two parties"
                # conversation. When sender or first recipient is missing
                # we leave thread_id null - the UI falls back to a
                # single-email rail selection.
                from_key = src.get("key") if src else None
                to_key = first_dst.get("key") if first_dst else None
                thread_id = None
                if from_key and to_key and from_key != to_key:
                    pair = sorted([from_key, to_key])
                    thread_id = f"emails-{report_key}-{pair[0]}-{pair[1]}"

                # Derive direction (incoming / outgoing) from the phone
                # owner's POV. The owner is the Person with
                # is_phone_owner=true on this device. If sender is owner
                # -> outgoing; if any recipient is owner -> incoming;
                # otherwise (rare; both external in a forwarded thread)
                # fall back to outgoing as a safe default.
                from_is_owner = bool(src.get("is_phone_owner")) if src else False
                any_dst_is_owner = any(d.get("is_phone_owner") for d in dsts)
                if from_is_owner:
                    direction = "outgoing"
                elif any_dst_is_owner:
                    direction = "incoming"
                else:
                    direction = "outgoing"

                rows.append({
                    "key": e.get("key"),
                    "id": e.get("id"),
                    "node_key": e.get("key"),
                    "timestamp": e.get("timestamp"),
                    "date": e.get("date"),
                    "time": e.get("time"),
                    "subject": e.get("subject"),
                    "source_app": e.get("source_app"),
                    "folder": e.get("folder"),
                    "email_status": e.get("email_status"),
                    "from_name": (src.get("name") if src else None),
                    "from_key": from_key,
                    "to_name": (first_dst.get("name") if first_dst else None),
                    "to_key": to_key,
                    "to_count": len(dsts),
                    "attachment_count": int(e.get("attachment_count") or 0),
                    "deleted_state": e.get("deleted_state"),
                    # Phase F additions: thread_id + direction so the UI
                    # can open the whole pair conversation in the rail
                    # and tag rows with in/out indicators.
                    "thread_id": thread_id,
                    "direction": direction,
                })
            return {"rows": rows, "total": total_count}

    def get_overview_contact_detail(
        self,
        case_id: str,
        report_key: str,
        contact_key: str,
        recent_limit: int = 50,
    ) -> Optional[dict]:
        """Fetch a single contact + their most recent comms with the phone owner."""
        with self._driver.session() as session:
            rec = session.run(
                """
                MATCH (p:Person {case_id: $case_id, key: $contact_key})
                RETURN p
                """,
                case_id=case_id,
                contact_key=contact_key,
            ).single()
            if not rec:
                return None
            p = dict(rec["p"])

            # Recent calls and messages involving this contact, on this device.
            # Traverse from the single Person outward - the previous form started
            # from every PhoneCall/Communication in the report and checked the
            # relationship for each, an O(N) scan per click on big phones.
            #
            # Direction is now derived from WHICH branch of the UNION matched
            # so the UI can show in/out arrows. From the phone owner's POV:
            #   - branch with (p)-[:CALLED]->(c)      -> contact CALLED owner = INCOMING
            #   - branch with (c)-[:CALLED_TO]->(p)   -> owner called CONTACT = OUTGOING
            #   - branch with (p)-[:SENT_MESSAGE]->(m) -> contact SENT m = INCOMING
            #   - participant branch: derive from m.sender_key vs contact_key
            calls_rs = session.run(
                """
                MATCH (p:Person {case_id: $case_id, key: $contact_key})
                CALL {
                    WITH p
                    MATCH (p)-[:CALLED]->(c:PhoneCall)
                    WHERE c.case_id = $case_id AND c.cellebrite_report_key = $rk
                    RETURN c, 'incoming' AS direction
                    UNION
                    WITH p
                    MATCH (c:PhoneCall)-[:CALLED_TO]->(p)
                    WHERE c.case_id = $case_id AND c.cellebrite_report_key = $rk
                    RETURN c, 'outgoing' AS direction
                }
                RETURN c, direction
                ORDER BY c.timestamp DESC
                LIMIT $lim
                """,
                case_id=case_id,
                rk=report_key,
                contact_key=contact_key,
                lim=int(recent_limit),
            )
            recent_calls = [(dict(r["c"]), r["direction"]) for r in calls_rs]

            # Messages: pull the sender key alongside so we can derive
            # direction (contact-sent = incoming, owner/other-sent =
            # outgoing). Also pull thread parent key so the UI can open
            # the conversation in the rail.
            msgs_rs = session.run(
                """
                MATCH (p:Person {case_id: $case_id, key: $contact_key})
                CALL {
                    WITH p
                    MATCH (p)-[:SENT_MESSAGE]->(m:Communication)
                    WHERE m.case_id = $case_id
                      AND m.cellebrite_report_key = $rk
                      AND m.body IS NOT NULL
                    OPTIONAL MATCH (m)-[:PART_OF]->(t:Communication)
                    RETURN m, p.key AS sender_key, t.key AS thread_id
                    UNION
                    WITH p
                    MATCH (p)-[:PARTICIPATED_IN]->(chat:Communication)<-[:PART_OF]-(m:Communication)
                    WHERE m.case_id = $case_id
                      AND m.cellebrite_report_key = $rk
                      AND m.body IS NOT NULL
                    OPTIONAL MATCH (sender:Person)-[:SENT_MESSAGE]->(m)
                    RETURN m, sender.key AS sender_key, chat.key AS thread_id
                }
                RETURN DISTINCT m, sender_key, thread_id
                ORDER BY m.timestamp DESC
                LIMIT $lim
                """,
                case_id=case_id,
                rk=report_key,
                contact_key=contact_key,
                lim=int(recent_limit),
            )
            recent_messages = [
                (dict(r["m"]), r["sender_key"], r["thread_id"])
                for r in msgs_rs
            ]

            return {
                "contact": {
                    "key": p.get("key"),
                    "name": p.get("name"),
                    "phone_numbers": list(p.get("phone_numbers") or []),
                    "is_phone_owner": bool(p.get("is_phone_owner")),
                    "cellebrite_id": p.get("cellebrite_id"),
                    "all_identifiers": list(p.get("all_identifiers") or []),
                },
                "recent_calls": [
                    {
                        "key": c.get("key"),
                        "timestamp": c.get("timestamp"),
                        # Derived from the relationship traversal above -
                        # not the raw c.direction property which can be
                        # ambiguous depending on which side recorded it.
                        "direction": direction,
                        "call_type": c.get("call_type"),
                        "duration": c.get("duration"),
                        "source_app": c.get("source_app"),
                    }
                    for (c, direction) in recent_calls
                ],
                "recent_messages": [
                    {
                        "key": m.get("key"),
                        "timestamp": m.get("timestamp"),
                        "source_app": m.get("source_app"),
                        "body": (m.get("body") or "")[:300],
                        # 'incoming' = sent BY this contact (so the
                        # phone owner received it). 'outgoing' = sent
                        # by anyone else in the chat (typically the
                        # owner; in group chats can be a third party).
                        "direction": (
                            "incoming" if sender_key == contact_key
                            else "outgoing"
                        ),
                        "sender_key": sender_key,
                        # Thread parent key - used by the UI to open the
                        # whole conversation in the rail anchored on
                        # this message.
                        "thread_id": thread_id,
                    }
                    for (m, sender_key, thread_id) in recent_messages
                ],
            }

    def get_contact_comms_feed(
        self,
        case_id: str,
        contact_key: str,
        report_keys: Optional[List[str]] = None,
        types: Optional[List[str]] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        """
        Chronological feed of every comm event involving a single Person,
        across all (or selected) devices. Used by the Communications tab
        drill-down drawer.

        types: subset of ['call', 'message', 'email'] - defaults to all three.
        """
        active = set(types) if types else {"call", "message", "email"}

        rk_filter = ""
        params: Dict[str, Any] = {"case_id": case_id, "contact_key": contact_key}
        if report_keys:
            rk_filter = "AND n.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        items: list = []

        # Look up the contact for the header
        with self._driver.session() as session:
            contact_rec = session.run(
                """
                MATCH (p:Person {case_id: $case_id, key: $contact_key})
                RETURN p LIMIT 1
                """,
                case_id=case_id,
                contact_key=contact_key,
            ).single()
            contact = dict(contact_rec["p"]) if contact_rec else {}

            # Calls - either direction
            if "call" in active:
                rs = session.run(
                    f"""
                    MATCH (p:Person {{case_id: $case_id, key: $contact_key}})
                    MATCH (n:PhoneCall {{case_id: $case_id, source_type: 'cellebrite'}})
                    WHERE ((p)-[:CALLED]->(n) OR (n)-[:CALLED_TO]->(p))
                      {rk_filter}
                    OPTIONAL MATCH (src:Person)-[:CALLED]->(n)
                    OPTIONAL MATCH (n)-[:CALLED_TO]->(dst:Person)
                    RETURN n, src, dst
                    ORDER BY n.timestamp DESC
                    LIMIT 2000
                    """,
                    params,
                )
                for rec in rs:
                    n = dict(rec["n"])
                    src = dict(rec["src"]) if rec["src"] else None
                    dst = dict(rec["dst"]) if rec["dst"] else None
                    items.append({
                        "id": n.get("id"),
                        "node_key": n.get("key"),
                        "type": "call",
                        "timestamp": n.get("timestamp"),
                        "source_app": n.get("source_app"),
                        "direction": n.get("direction"),
                        "call_type": n.get("call_type"),
                        "duration": n.get("duration"),
                        "video_call": bool(n.get("video_call")),
                        "deleted_state": n.get("deleted_state"),
                        "report_key": n.get("cellebrite_report_key"),
                        "attachment_file_ids": list(n.get("attachment_file_ids") or []),
                        "sender": {
                            "key": (src.get("key") if src else None),
                            "name": (src.get("name") if src else None),
                            "is_owner": bool(src.get("is_phone_owner")) if src else False,
                        } if src else None,
                        "recipient": {
                            "key": (dst.get("key") if dst else None),
                            "name": (dst.get("name") if dst else None),
                            "is_owner": bool(dst.get("is_phone_owner")) if dst else False,
                        } if dst else None,
                    })

            # Messages - either as sender, or as participant in a chat
            if "message" in active:
                rs = session.run(
                    f"""
                    MATCH (p:Person {{case_id: $case_id, key: $contact_key}})
                    MATCH (n:Communication {{case_id: $case_id, source_type: 'cellebrite'}})
                    WHERE n.body IS NOT NULL
                      AND (
                        (p)-[:SENT_MESSAGE]->(n)
                        OR EXISTS {{
                          MATCH (n)-[:PART_OF]->(chat:Communication)<-[:PARTICIPATED_IN]-(p)
                        }}
                      )
                      {rk_filter}
                    OPTIONAL MATCH (sender:Person)-[:SENT_MESSAGE]->(n)
                    OPTIONAL MATCH (n)-[:PART_OF]->(chat:Communication)
                    RETURN n, sender, chat
                    ORDER BY n.timestamp DESC
                    LIMIT 4000
                    """,
                    params,
                )
                for rec in rs:
                    n = dict(rec["n"])
                    sender = dict(rec["sender"]) if rec["sender"] else None
                    chat = dict(rec["chat"]) if rec["chat"] else None
                    body = n.get("body") or ""
                    items.append({
                        "id": n.get("id"),
                        "node_key": n.get("key"),
                        "type": "message",
                        "timestamp": n.get("timestamp"),
                        "source_app": n.get("source_app"),
                        "message_type": n.get("message_type"),
                        "body": body,
                        "deleted_state": n.get("deleted_state"),
                        "report_key": n.get("cellebrite_report_key"),
                        "attachment_file_ids": list(n.get("attachment_file_ids") or []),
                        "thread_id": (chat.get("key") if chat else None),
                        "thread_name": (chat.get("name") if chat else None),
                        "sender": {
                            "key": (sender.get("key") if sender else None),
                            "name": (sender.get("name") if sender else None),
                            "is_owner": bool(sender.get("is_phone_owner")) if sender else False,
                        } if sender else None,
                    })

            # Emails - sent or received
            if "email" in active:
                rs = session.run(
                    f"""
                    MATCH (p:Person {{case_id: $case_id, key: $contact_key}})
                    MATCH (n:Email {{case_id: $case_id, source_type: 'cellebrite'}})
                    WHERE ((p)-[:EMAILED]->(n) OR (n)-[:SENT_TO]->(p))
                      {rk_filter}
                    OPTIONAL MATCH (src:Person)-[:EMAILED]->(n)
                    OPTIONAL MATCH (n)-[:SENT_TO]->(dst:Person)
                    WITH n, src, collect(DISTINCT dst) AS dsts
                    RETURN n, src, dsts
                    ORDER BY n.timestamp DESC
                    LIMIT 1000
                    """,
                    params,
                )
                for rec in rs:
                    n = dict(rec["n"])
                    src = dict(rec["src"]) if rec["src"] else None
                    dsts = [dict(d) for d in rec["dsts"] if d is not None]
                    first_dst = dsts[0] if dsts else None
                    items.append({
                        "id": n.get("id"),
                        "node_key": n.get("key"),
                        "type": "email",
                        "timestamp": n.get("timestamp"),
                        "source_app": n.get("source_app"),
                        "subject": n.get("subject"),
                        "body": n.get("body") or "",
                        "folder": n.get("folder"),
                        "email_status": n.get("email_status"),
                        "deleted_state": n.get("deleted_state"),
                        "report_key": n.get("cellebrite_report_key"),
                        "attachment_file_ids": list(n.get("attachment_file_ids") or []),
                        "sender": {
                            "key": (src.get("key") if src else None),
                            "name": (src.get("name") if src else None),
                            "is_owner": bool(src.get("is_phone_owner")) if src else False,
                        } if src else None,
                        "recipient": {
                            "key": (first_dst.get("key") if first_dst else None),
                            "name": (first_dst.get("name") if first_dst else None),
                            "is_owner": bool(first_dst.get("is_phone_owner")) if first_dst else False,
                        } if first_dst else None,
                        "recipient_count": len(dsts),
                    })

        # Sort newest-first, paginate
        items.sort(key=lambda i: (i.get("timestamp") or ""), reverse=True)
        total = len(items)
        items = items[offset: offset + limit]

        return {
            "contact": {
                "key": contact.get("key"),
                "name": contact.get("name"),
                "phone_numbers": list(contact.get("phone_numbers") or []),
                "is_phone_owner": bool(contact.get("is_phone_owner")),
                "all_identifiers": list(contact.get("all_identifiers") or []),
            } if contact else None,
            "items": items,
            "total": total,
        }

    def resolve_file_parents(
        self,
        case_id: str,
        model_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Resolve attachment model IDs to their parent Cellebrite graph nodes."""
        return resolve_file_parents(self._driver, case_id, model_ids)


def _build_match_snippet(text: str, term: str, context_chars: int = 60) -> str:
    """
    Return a one-line preview of `text` centred on the first
    case-insensitive occurrence of `term`, with up to `context_chars`
    bytes of surrounding context. Used by /comms/messages/search to
    show "...that's why I called - Monday morning..." style previews.
    """
    if not text:
        return ""
    if not term:
        return text[: 2 * context_chars + 50]
    haystack_lower = text.lower()
    needle_lower = term.lower()
    idx = haystack_lower.find(needle_lower)
    if idx < 0:
        # Caller already established a match - defensive fallback.
        return text[: 2 * context_chars + 50]
    start = max(0, idx - context_chars)
    end = min(len(text), idx + len(term) + context_chars)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    # Collapse runs of whitespace so the snippet is one clean line.
    snippet = " ".join(snippet.split())
    return snippet


def _project_event(node, event_type: str) -> Optional[dict]:
    """Base projection for event-like nodes into the unified shape."""
    if not node:
        return None
    n = dict(node)
    lat = n.get("latitude") if n.get("latitude") is not None else n.get("nearest_location_lat")
    lon = n.get("longitude") if n.get("longitude") is not None else n.get("nearest_location_lon")
    is_geo = lat is not None and lon is not None
    direct_geo = n.get("latitude") is not None and n.get("longitude") is not None
    loc_source = "direct" if direct_geo else ("nearest" if is_geo else "none")

    label = n.get("name") or event_type.title()
    return {
        "id": n.get("id") or n.get("key"),
        "node_key": n.get("key"),
        "label": label,
        "summary": (n.get("body") or n.get("summary") or n.get("name") or "")[:200],
        "timestamp": n.get("timestamp"),
        "latitude": lat,
        "longitude": lon,
        "source_app": n.get("source_app"),
        "direction": n.get("direction"),
        "duration": n.get("duration") or n.get("duration_s"),
        "device_report_key": n.get("cellebrite_report_key"),
        "counterpart": None,
        "thread_id": None,
        "is_geolocated": bool(is_geo),
        "location_source": loc_source,
        # Per-point precision in metres if Cellebrite carried it (or
        # CellTower's radius). Frontend uses this to render a halo so
        # the user can see uncertainty without opening the detail rail.
        "accuracy_meters": n.get("accuracy_meters"),
        # Either a numeric carving confidence or a string label
        # ("High"/"Medium"/"Low"). Pass through unchanged so the UI can
        # decide rendering - we don't fabricate scores we didn't see.
        "confidence_score": n.get("confidence_score"),
        # Free-form address composed at ingestion from PositionAddress
        # sub-fields, or reverse-geocoded via the configured Nominatim
        # / GeoNames backend when Cellebrite didn't carry one.
        "address": n.get("address"),
        # Reverse-geocoded admin levels - populated when GEOCODER is
        # configured at ingestion time. `geocode_source` tells the UI
        # which path produced the address ("cellebrite" / "nominatim"
        # / "geonames" / "none") so it can label inferred data honestly.
        "place_name": n.get("place_name"),
        "country": n.get("country"),
        "country_code": n.get("country_code"),
        "admin1": n.get("admin1"),
        "admin2": n.get("admin2"),
        "geocode_source": n.get("geocode_source"),
        "geocode_accuracy": n.get("geocode_accuracy"),
        "attachment_count": int(n.get("attachment_count") or 0),
        "state": n.get("state"),
        "app_name": n.get("app_name"),
    }


def _project_call(node, src, dst) -> Optional[dict]:
    row = _project_event(node, "call")
    if not row:
        return None
    n = dict(node)
    label = "Call"
    if n.get("direction"):
        label = f"Call ({n['direction']})"
    if n.get("call_type") and n.get("call_type") != "Regular":
        label += f" - {n['call_type']}"
    row["label"] = label
    counter_node = dst if (src is None or (src and dict(src).get("is_phone_owner"))) else src
    if counter_node:
        c = dict(counter_node)
        row["counterpart"] = {"key": c.get("key"), "name": c.get("name") or c.get("key")}
    return row


def _project_message(node, sender, chat) -> Optional[dict]:
    row = _project_event(node, "message")
    if not row:
        return None
    n = dict(node)
    row["label"] = (n.get("source_app") or "Message") + " message"
    row["summary"] = (n.get("body") or "")[:200]
    if sender:
        s = dict(sender)
        row["counterpart"] = {"key": s.get("key"), "name": s.get("name") or s.get("key")}
    if chat:
        row["thread_id"] = dict(chat).get("key")
    return row


def _project_email(node, src, dst) -> Optional[dict]:
    row = _project_event(node, "email")
    if not row:
        return None
    n = dict(node)
    row["label"] = "Email"
    row["summary"] = (n.get("subject") or n.get("body") or "")[:200]
    counter_node = dst if (src is None or (src and dict(src).get("is_phone_owner"))) else src
    if counter_node:
        c = dict(counter_node)
        row["counterpart"] = {"key": c.get("key"), "name": c.get("name") or c.get("key")}
    return row


def _simplify_points(points: List[dict], min_dist_m: float = 50.0, min_time_s: float = 60.0) -> List[dict]:
    """Drop consecutive points closer than (min_dist_m AND min_time_s) to the previous kept point."""
    import math
    if not points:
        return points
    def haversine(a, b):
        R = 6371000.0
        lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
        dlat = lat2 - lat1
        dlon = math.radians(b["lon"] - a["lon"])
        h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        return 2 * R * math.asin(math.sqrt(h))
    def _ts_sec(p):
        try:
            from datetime import datetime
            return datetime.fromisoformat((p["timestamp"] or "").replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0
    out = [points[0]]
    last = points[0]
    last_t = _ts_sec(last)
    for p in points[1:]:
        t = _ts_sec(p)
        if haversine(last, p) < min_dist_m and abs(t - last_t) < min_time_s:
            continue
        out.append(p)
        last = p
        last_t = t
    return out


def resolve_file_parents(
    driver,
    case_id: str,
    model_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    """
    For a batch of Cellebrite model_ids, return a map model_id -> {label, name, source_app, key}.
    Used by the Files Explorer to show "this attachment belongs to Chat (WhatsApp)".
    """
    if not model_ids:
        return {}
    ids = [m for m in model_ids if m]
    if not ids:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    with driver.session() as session:
        rs = session.run(
            """
            MATCH (n {case_id: $case_id, source_type: 'cellebrite'})
            WHERE n.cellebrite_id IN $ids
            RETURN n.cellebrite_id AS mid,
                   labels(n)[0] AS label,
                   n.name AS name,
                   n.source_app AS source_app,
                   n.key AS key,
                   n.body AS body,
                   n.subject AS subject,
                   n.timestamp AS timestamp
            """,
            case_id=case_id,
            ids=ids,
        )
        for rec in rs:
            mid = rec["mid"]
            if not mid:
                continue
            out[mid] = {
                "label": rec["label"],
                "name": rec["name"] or rec["subject"] or (rec["body"] or "")[:60],
                "source_app": rec["source_app"],
                "key": rec["key"],
                "timestamp": rec["timestamp"],
            }
    return out


cellebrite_service = CellebriteNeo4jService()
