"""
Main orchestrator for Cellebrite UFED report ingestion.

Ties together the streaming XML parser, Neo4j writer, and file linker
into a single pipeline that processes a Cellebrite report folder into
the Neo4j knowledge graph.

Usage:
    from cellebrite.ingestion import ingest_cellebrite_report

    result = ingest_cellebrite_report(
        report_dir=Path("/path/to/report"),
        case_id="case-123",
        log_callback=print,
    )
"""

import time
from pathlib import Path
from typing import Optional, Callable, List

from .parser import CellebriteXMLParser
from .neo4j_writer import CellebriteNeo4jWriter
from .file_linker import CellebriteFileLinker
from .models import ParsedModel


def detect_cellebrite_xml(report_dir: Path) -> Optional[Path]:
    """
    Find the Cellebrite UFED XML report file in a directory.

    Looks for XML files containing the Cellebrite namespace in the first 4KB.
    Returns the path to the XML file, or None if not found.
    """
    CELLEBRITE_NS = "http://pa.cellebrite.com/report/2.0"

    for xml_file in report_dir.glob("*.xml"):
        try:
            with open(xml_file, "r", encoding="utf-8", errors="ignore") as f:
                header = f.read(4096)
            if CELLEBRITE_NS in header:
                return xml_file
        except (OSError, IOError):
            continue

    return None


def ingest_cellebrite_report(
    report_dir: Path,
    case_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
    profile_name: Optional[str] = None,
    owner: Optional[str] = None,
    evidence_storage=None,
) -> dict:
    """
    Ingest a complete Cellebrite UFED report into the Neo4j graph.

    Args:
        report_dir: Path to the Cellebrite report folder
        case_id: Case ID for graph isolation
        log_callback: Progress logging callback
        profile_name: LLM profile name (unused in Tier 1, passed for compatibility)
        owner: Username for evidence record ownership
        evidence_storage: EvidenceStorage instance for registering media files

    Returns:
        Dict with ingestion statistics and status
    """
    start_time = time.time()

    def _log(msg: str):
        if log_callback:
            log_callback(msg)

    # ------------------------------------------------------------------
    # Step 1: Detect and validate XML
    # ------------------------------------------------------------------
    _log("Step 1/9: Detecting Cellebrite XML report...")

    xml_path = detect_cellebrite_xml(report_dir)
    if not xml_path:
        _log("ERROR: No Cellebrite UFED XML found in directory")
        return {
            "status": "error",
            "reason": "no_cellebrite_xml",
            "file": str(report_dir),
        }

    _log(f"Found report: {xml_path.name}")

    # ------------------------------------------------------------------
    # Step 2: Parse report header
    # ------------------------------------------------------------------
    _log("Step 2/9: Parsing report header...")

    parser = CellebriteXMLParser(xml_path, log_callback=log_callback)
    report = parser.parse_header()

    # Generate unique report key
    report_key = (
        f"cellebrite-{report.case_info.case_number or 'unknown'}"
        f"-{report.case_info.evidence_number or 'unknown'}"
    )

    # ------------------------------------------------------------------
    # Step 3: Parse tagged files (file index)
    # ------------------------------------------------------------------
    _log("Step 3/9: Building file index from tagged files...")

    tagged_files = parser.parse_tagged_files()

    # ------------------------------------------------------------------
    # Step 4: Build file linker
    # ------------------------------------------------------------------
    _log("Step 4/9: Resolving file paths...")

    file_linker = CellebriteFileLinker(
        report_dir=report_dir,
        tagged_files=tagged_files,
        case_id=case_id,
        report_key=report_key,
        log_callback=log_callback,
    )

    # ------------------------------------------------------------------
    # Step 5: Create Neo4j writer and PhoneReport node
    # ------------------------------------------------------------------
    _log("Step 5/9: Creating PhoneReport node in Neo4j...")

    # Import Neo4j client here to avoid import issues when running
    # from different working directories
    import sys
    scripts_dir = Path(__file__).resolve().parent.parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    from neo4j_client import Neo4jClient

    db = Neo4jClient()
    writer = CellebriteNeo4jWriter(
        neo4j_client=db,
        case_id=case_id,
        report_key=report_key,
        report=report,
        log_callback=log_callback,
    )

    writer.create_phone_report_node()

    # ------------------------------------------------------------------
    # Step 6: First pass — collect phone owner identity
    # ------------------------------------------------------------------
    _log("Step 6/9: Identifying phone owner (first pass)...")

    # We need a first pass through models to find the phone owner
    # before writing anything, so we can link entities correctly.
    # Collect all models first, then write.
    all_models: List[ParsedModel] = []

    for batch in parser.stream_models(batch_size=500):
        for model in batch:
            writer.collect_phone_owner_info([model])
            all_models.append(model)

    phone_owner_key = writer.create_phone_owner()
    if phone_owner_key:
        writer.link_phone_owner_to_report()

    _log(f"Collected {len(all_models)} models for processing")

    # ------------------------------------------------------------------
    # Step 7: Build model-to-file mapping from jump targets
    # ------------------------------------------------------------------
    _log("Step 7/9: Mapping file references...")

    model_file_map = file_linker.build_model_file_map(all_models)
    _log(f"Found {sum(len(v) for v in model_file_map.values())} file references across {len(model_file_map)} models")

    # Make the attachment mapping available to the writer so that message/email/call
    # nodes are persisted with `attachment_file_ids` for downstream retrieval.
    writer.attachment_map = model_file_map

    # ------------------------------------------------------------------
    # Step 8: Write all models to Neo4j
    # ------------------------------------------------------------------
    _log("Step 8/9: Writing models to Neo4j...")

    batch_size = 200
    for i in range(0, len(all_models), batch_size):
        batch = all_models[i:i + batch_size]
        writer.write_batch(batch)

        processed = min(i + batch_size, len(all_models))
        if processed % 1000 == 0 or processed == len(all_models):
            pct = 100 * processed / max(len(all_models), 1)
            _log(f"Written {processed}/{len(all_models)} models ({pct:.1f}%)")

    # ------------------------------------------------------------------
    # Step 8.5: Geotag backfill for comms events
    # ------------------------------------------------------------------
    _log("Step 8.5: Backfilling nearest-location tags on comms events...")
    try:
        backfill_stats = _backfill_nearest_location(db, case_id, report_key, log_callback=log_callback)
        _log(
            f"Backfill: "
            f"{backfill_stats['calls_tagged']} calls, "
            f"{backfill_stats['messages_tagged']} messages, "
            f"{backfill_stats['emails_tagged']} emails tagged "
            f"(within {backfill_stats['window_minutes']} min window)"
        )
    except Exception as e:
        _log(f"WARNING: Geotag backfill failed: {e}")

    # ------------------------------------------------------------------
    # Step 9: Register media files as evidence records
    # ------------------------------------------------------------------
    media_registered = 0
    if evidence_storage:
        _log("Step 9/9: Registering media files as evidence records...")
        media_registered = file_linker.register_media_files(
            evidence_storage=evidence_storage,
            owner=owner,
            model_file_map=model_file_map,
        )
    else:
        _log("Step 9/9: Skipping media registration (no evidence storage)")

    # ------------------------------------------------------------------
    # Done — compile statistics
    # ------------------------------------------------------------------
    elapsed = time.time() - start_time
    stats = writer.get_stats()
    stats.update({
        "status": "success",
        "report_key": report_key,
        "report_name": report.report_name,
        "case_number": report.case_info.case_number,
        "evidence_number": report.case_info.evidence_number,
        "xml_model_count": report.model_count,
        "xml_node_count": report.node_count,
        "tagged_files_total": file_linker.total_count,
        "tagged_files_resolved": file_linker.resolved_count,
        "media_files_registered": media_registered,
        "model_file_references": sum(len(v) for v in model_file_map.values()),
        "duration_seconds": round(elapsed, 1),
    })

    _log(
        f"\nIngestion complete in {elapsed:.1f}s:\n"
        f"  Contacts: {stats['contacts_created']}\n"
        f"  Calls: {stats['calls_created']}\n"
        f"  Chats: {stats['chats_created']}\n"
        f"  Messages: {stats['messages_created']}\n"
        f"  Emails: {stats['emails_created']}\n"
        f"  Locations: {stats['locations_created']}\n"
        f"  Accounts: {stats['accounts_created']}\n"
        f"  Searches: {stats['searches_created']}\n"
        f"  Pages: {stats['visited_pages_created']}\n"
        f"  Meetings: {stats['meetings_created']}\n"
        f"  Devices: {stats['devices_created']}\n"
        f"  WiFi: {stats['wifi_networks_created']}\n"
        f"  Credentials: {stats['credentials_created']}\n"
        f"  Bookmarks: {stats['bookmarks_created']}\n"
        f"  Total nodes: {stats['total_nodes']}\n"
        f"  Total relationships: {stats['total_relationships']}\n"
        f"  Media files registered: {media_registered}\n"
        f"  Phone owner: {stats['phone_owner']}"
    )

    db.close()
    return stats


# ---------------------------------------------------------------------------
# Phase 4 helper: geotag backfill
# ---------------------------------------------------------------------------


def _backfill_nearest_location(
    db,
    case_id: str,
    report_key: str,
    window_minutes: int = 15,
    log_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    For each PhoneCall / Communication(message) / Email in the given report,
    find the nearest-in-time Location or CellTower within ±window_minutes and
    write nearest_location_* properties on the node.

    This turns non-geotagged comms events into map-displayable ones using
    the device's own location fixes as a proxy.
    """
    import bisect
    from datetime import datetime, timedelta

    def _log(msg: str):
        if log_callback:
            log_callback(msg)

    def _parse_ts(raw: str):
        """Parse an ISO timestamp to a naive UTC datetime.

        Timestamps in Cellebrite reports may or may not include a timezone
        offset. Normalising to naive-UTC lets us compare them with bisect
        without TypeErrors from mixing aware and naive datetimes.
        """
        if not raw:
            return None
        try:
            from datetime import timezone as _tz
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        if dt.tzinfo is not None:
            # Convert to UTC, then drop tzinfo so everything is comparable
            from datetime import timezone as _tz
            dt = dt.astimezone(_tz.utc).replace(tzinfo=None)
        return dt

    # Build timeline of geolocated anchor points (Locations + CellTowers)
    anchors: List[tuple] = []  # (datetime, node_key, lat, lon, source)
    with db._driver.session() as session:
        rs = session.run(
            """
            MATCH (l:Location {case_id: $cid, cellebrite_report_key: $rk})
            WHERE l.latitude IS NOT NULL AND l.longitude IS NOT NULL AND l.timestamp IS NOT NULL
            RETURN l.key AS k, l.latitude AS lat, l.longitude AS lon, l.timestamp AS ts, 'location' AS src
            UNION ALL
            MATCH (c:CellTower {case_id: $cid, cellebrite_report_key: $rk})
            WHERE c.latitude IS NOT NULL AND c.longitude IS NOT NULL AND c.timestamp IS NOT NULL
            RETURN c.key AS k, c.latitude AS lat, c.longitude AS lon, c.timestamp AS ts, 'cell_tower' AS src
            """,
            cid=case_id,
            rk=report_key,
        )
        for r in rs:
            dt = _parse_ts(r["ts"])
            if dt:
                anchors.append((dt, r["k"], r["lat"], r["lon"], r["src"]))

    anchors.sort(key=lambda a: a[0])
    anchor_times = [a[0] for a in anchors]
    window = timedelta(minutes=window_minutes)

    def _find_nearest(ts: datetime):
        if not anchors:
            return None
        idx = bisect.bisect_left(anchor_times, ts)
        candidates = []
        if idx < len(anchors):
            candidates.append(anchors[idx])
        if idx > 0:
            candidates.append(anchors[idx - 1])
        best = None
        best_delta = None
        for c in candidates:
            delta = abs((c[0] - ts).total_seconds())
            if delta <= window.total_seconds() and (best_delta is None or delta < best_delta):
                best = c
                best_delta = delta
        if best is None:
            return None
        return best + (best_delta,)  # append delta_s

    stats = {
        "window_minutes": window_minutes,
        "anchor_count": len(anchors),
        "calls_tagged": 0,
        "messages_tagged": 0,
        "emails_tagged": 0,
    }

    if not anchors:
        _log("Backfill: no anchor points (Locations/CellTowers) with coords — skipping")
        return stats

    # Backfill each label in batches
    label_keys = [
        ("PhoneCall", "calls_tagged"),
        ("Communication", "messages_tagged"),
        ("Email", "emails_tagged"),
    ]

    for label, stat_key in label_keys:
        extra_where = "AND n.body IS NOT NULL" if label == "Communication" else ""
        with db._driver.session() as session:
            rs = session.run(
                f"""
                MATCH (n:{label} {{case_id: $cid, cellebrite_report_key: $rk}})
                WHERE n.timestamp IS NOT NULL {extra_where}
                RETURN n.key AS k, n.timestamp AS ts, n.latitude AS lat, n.longitude AS lon
                """,
                cid=case_id,
                rk=report_key,
            )
            updates = []
            for r in rs:
                ts = _parse_ts(r["ts"])
                if not ts:
                    continue
                direct = r["lat"] is not None and r["lon"] is not None
                if direct:
                    updates.append({
                        "key": r["k"],
                        "nearest_location_key": None,
                        "nearest_location_lat": r["lat"],
                        "nearest_location_lon": r["lon"],
                        "nearest_location_delta_s": 0,
                        "nearest_location_source": "direct",
                        "location_source": "direct",
                    })
                    continue
                found = _find_nearest(ts)
                if found is None:
                    updates.append({
                        "key": r["k"],
                        "nearest_location_key": None,
                        "nearest_location_lat": None,
                        "nearest_location_lon": None,
                        "nearest_location_delta_s": None,
                        "nearest_location_source": "none",
                        "location_source": "none",
                    })
                    continue
                anchor_dt, anchor_key, lat, lon, src, delta = found
                updates.append({
                    "key": r["k"],
                    "nearest_location_key": anchor_key,
                    "nearest_location_lat": lat,
                    "nearest_location_lon": lon,
                    "nearest_location_delta_s": int(delta),
                    "nearest_location_source": src,
                    "location_source": "nearest",
                })

            # Batch write updates
            if updates:
                batch_size = 500
                for i in range(0, len(updates), batch_size):
                    chunk = updates[i:i + batch_size]
                    session.run(
                        f"""
                        UNWIND $rows AS row
                        MATCH (n:{label} {{case_id: $cid, key: row.key}})
                        SET n.nearest_location_key = row.nearest_location_key,
                            n.nearest_location_lat = row.nearest_location_lat,
                            n.nearest_location_lon = row.nearest_location_lon,
                            n.nearest_location_delta_s = row.nearest_location_delta_s,
                            n.nearest_location_source = row.nearest_location_source,
                            n.location_source = row.location_source
                        """,
                        cid=case_id,
                        rows=chunk,
                    )
                # Count only tagged (direct or nearest)
                tagged = sum(1 for u in updates if u["location_source"] in ("direct", "nearest"))
                stats[stat_key] = tagged

    return stats
