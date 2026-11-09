"""Re-evaluate ingestion-time geocodes for one case.

This maintenance command is deliberately case-scoped and skips every node whose
location was manually corrected.  Pass ``--apply`` to persist the recalculated
results; without it, the command only reports what it would inspect.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from app.ontology import load_ontology
from app.services import neo4j_client
from app.services.geocoding import NOT_RUN_STATUS, build_geocode_request, geocoding_service


_MANUAL_LOCATION_FIELDS = {
    "address",
    "city",
    "country",
    "latitude",
    "location_formatted",
    "location_name",
    "location_raw",
    "longitude",
    "region",
}
_GEOCODABLE_CATEGORIES = set(load_ontology().geocodable_categories)


async def _clear_ungeocodable(case_id: str, key: str) -> None:
    await neo4j_client.execute_write(
        """
        MATCH (n {case_id: $case_id, key: $key})
        REMOVE n.latitude,
               n.longitude,
               n.location_formatted,
               n.location_granularity,
               n.geocoding_status,
               n.geocoding_confidence,
               n.geocoding_provider,
               n.geocoding_provider_importance,
               n.geocoding_query,
               n.geocoding_formatted_address
        """,
        {"case_id": case_id, "key": key},
    )


async def _store_unsuccessful(
    case_id: str,
    key: str,
    *,
    location_raw: str,
    location_specificity: str,
    status: str,
    provider: str,
    query: str,
) -> None:
    await neo4j_client.execute_write(
        """
        MATCH (n {case_id: $case_id, key: $key})
        REMOVE n.latitude,
               n.longitude,
               n.location_formatted,
               n.location_granularity,
               n.geocoding_confidence,
               n.geocoding_provider_importance,
               n.geocoding_formatted_address
        SET n.location_raw = $location_raw,
            n.location_specificity = $location_specificity,
            n.geocoding_status = $status,
            n.geocoding_provider = $provider,
            n.geocoding_query = $query
        """,
        {
            "case_id": case_id,
            "key": key,
            "location_raw": location_raw,
            "location_specificity": location_specificity,
            "status": status,
            "provider": provider,
            "query": query,
        },
    )


async def _store_success(case_id: str, key: str, result: Any) -> None:
    await neo4j_client.execute_write(
        """
        MATCH (n {case_id: $case_id, key: $key})
        SET n.latitude = $latitude,
            n.longitude = $longitude,
            n.location_formatted = $formatted_address,
            n.location_granularity = $location_granularity,
            n.geocoding_status = 'success',
            n.geocoding_confidence = $confidence,
            n.geocoding_provider = $provider,
            n.geocoding_provider_importance = $provider_importance,
            n.geocoding_query = $query,
            n.geocoding_formatted_address = $formatted_address
        """,
        {
            "case_id": case_id,
            "key": key,
            "latitude": result.latitude,
            "longitude": result.longitude,
            "formatted_address": result.formatted_address,
            "location_granularity": result.location_granularity,
            "confidence": result.confidence,
            "provider": result.provider,
            "provider_importance": result.provider_importance,
            "query": result.original_query,
        },
    )


def _refused_on_recheck(result: Any) -> bool:
    return bool((result.raw_response or {}).get("rechecked"))


async def regeocode_case(case_id: str, *, apply: bool, only_refused: bool = False) -> dict[str, Any]:
    """``only_refused``: clear only the pins whose stored answer today's checks refuse, asking no geocoder and
    leaving every other node as it is (the not-geocodable rule included)."""
    rows = await neo4j_client.execute_query(
        """
        MATCH (n {case_id: $case_id})
        WHERE n.geocoding_status IS NOT NULL
           OR (n.latitude IS NOT NULL AND n.longitude IS NOT NULL)
        RETURN n.key AS key,
               n.name AS name,
               labels(n)[0] AS category,
               properties(n) AS properties
        ORDER BY category, name
        """,
        {"case_id": case_id},
    )
    counts = {
        "inspected": len(rows),
        "skipped_manual": 0,
        "not_geocodable": 0,
        "success": 0,
        "ambiguous": 0,
        "failed": 0,
        # No geocoder on this server and nothing stored for the request: the pin is left as it is, since nothing
        # can check it (clearing it would lose a pin that may be right).
        "not_run": 0,
        "would_clear": 0,
        "would_keep": 0,
        "would_keep_unchecked": 0,
    }
    details: list[dict[str, Any]] = []

    for row in rows:
        category = str(row["category"] or "")
        properties = dict(row["properties"] or {})
        manual_fields = set(properties.get("manual_fields") or [])
        if manual_fields & _MANUAL_LOCATION_FIELDS:
            counts["skipped_manual"] += 1
            continue
        if category not in _GEOCODABLE_CATEGORIES:
            continue

        request = build_geocode_request(category, str(row["name"] or ""), properties)
        if request is None:
            counts["not_geocodable"] += 1
            details.append(
                {"key": row["key"], "name": row["name"], "status": "not_geocodable",
                 "pinned_at": properties.get("location_formatted")
                 if properties.get("latitude") is not None else None}
            )
            if apply and not only_refused:
                await _clear_ungeocodable(case_id, str(row["key"]))
            continue

        if not apply:
            stored = await geocoding_service.cached_only(request)
            has_pin = properties.get("latitude") is not None
            if stored is None:
                status = "would_geocode"
            elif stored.status == "success":
                status = "would_keep"
            elif has_pin and not _refused_on_recheck(stored):
                status = "would_keep_unchecked"
            else:
                status = "would_clear" if has_pin else "would_stay_unplaced"
            if status in counts:
                counts[status] += 1
            details.append(
                {
                    "key": row["key"],
                    "name": row["name"],
                    "status": status,
                    "query": request.query,
                    "pinned_at": properties.get("location_formatted"),
                    "reason": ((stored.raw_response or {}).get("rejection_reason") if stored else None),
                }
            )
            continue

        has_pin = properties.get("latitude") is not None
        if only_refused:
            stored = await geocoding_service.cached_only(request)
            if not (has_pin and stored is not None and _refused_on_recheck(stored)):
                continue
            counts["cleared_refused"] = counts.get("cleared_refused", 0) + 1
            details.append({"key": row["key"], "name": row["name"], "status": "cleared_refused",
                            "query": request.query, "was_pinned_at": properties.get("location_formatted"),
                            "reason": (stored.raw_response or {}).get("rejection_reason")})
            await _store_unsuccessful(
                case_id,
                str(row["key"]),
                location_raw=request.location_raw,
                location_specificity=request.location_specificity,
                status=stored.status,
                provider=stored.provider,
                query=stored.original_query,
            )
            continue

        result = await geocoding_service.geocode(request)
        counts[result.status] = counts.get(result.status, 0) + 1
        if result.status == NOT_RUN_STATUS or (
            result.status != "success" and has_pin and not _refused_on_recheck(result)
        ):
            # A pin is cleared only when the stored answer that placed it is refused by today's checks. A stored
            # refusal for this request says nothing about a pin placed some other way (an earlier, coarser lookup:
            # "Querétaro, Mexico" is right where it is), so that pin stays.
            counts["kept_unchecked"] = counts.get("kept_unchecked", 0) + 1
            details.append({"key": row["key"], "name": row["name"], "status": "kept_unchecked"})
            continue
        details.append(
            {
                "key": row["key"],
                "name": row["name"],
                "status": result.status,
                "confidence": result.confidence,
                "formatted_address": result.formatted_address,
            }
        )
        if result.status == "success":
            await _store_success(case_id, str(row["key"]), result)
        else:
            await _store_unsuccessful(
                case_id,
                str(row["key"]),
                location_raw=request.location_raw,
                location_specificity=request.location_specificity,
                status=result.status,
                provider=result.provider,
                query=result.original_query,
            )

    return {"case_id": case_id, "applied": apply, "counts": counts, "details": details}


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--only-refused",
        action="store_true",
        help="with --apply: clear only pins whose stored answer today's checks refuse; ask no geocoder",
    )
    args = parser.parse_args()
    try:
        report = await regeocode_case(args.case_id, apply=args.apply, only_refused=args.only_refused)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        await neo4j_client.close_neo4j()


if __name__ == "__main__":
    asyncio.run(_main())
