"""
Financial Router - endpoints for financial analysis and transaction visualization.
"""

import json
import logging
import math
import traceback
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Query, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from services import neo4j_service
from services.financial_export_service import generate_financial_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/financial", tags=["financial"])


class CategorizeRequest(BaseModel):
    category: str
    case_id: str


class FromToRequest(BaseModel):
    case_id: str
    from_key: Optional[str] = None
    from_name: Optional[str] = None
    to_key: Optional[str] = None
    to_name: Optional[str] = None


class BatchCategorizeRequest(BaseModel):
    node_keys: List[str]
    category: str
    case_id: str


class DetailsRequest(BaseModel):
    case_id: str
    purpose: Optional[str] = None
    counterparty_details: Optional[str] = None
    notes: Optional[str] = None


class BatchFromToRequest(BaseModel):
    node_keys: List[str]
    case_id: str
    from_key: Optional[str] = None
    from_name: Optional[str] = None
    to_key: Optional[str] = None
    to_name: Optional[str] = None


class CreateCategoryRequest(BaseModel):
    name: str
    color: str
    case_id: str


@router.get("")
async def get_financial_transactions(
    case_id: str = Query(..., description="REQUIRED: Filter to transactions in this case"),
    types: Optional[str] = Query(None, description="Comma-separated transaction types to include"),
    start_date: Optional[str] = Query(None, description="Filter on or after this date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter on or before this date (YYYY-MM-DD)"),
    categories: Optional[str] = Query(None, description="Comma-separated financial categories to include"),
):
    """
    Get financial transactions with from/to entity resolution for a specific case.
    """
    try:
        parsed_types = [t.strip() for t in types.split(",") if t.strip()] if types else None
        parsed_categories = [c.strip() for c in categories.split(",") if c.strip()] if categories else None

        transactions = neo4j_service.get_financial_transactions(
            case_id=case_id,
            types=parsed_types,
            start_date=start_date,
            end_date=end_date,
            categories=parsed_categories,
        )
        return {"transactions": transactions, "total": len(transactions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/query")
async def query_financial(
    case_id: str = Query(..., description="REQUIRED: Case ID"),
    types: Optional[str] = Query(None, description="Comma-separated transaction types"),
    categories: Optional[str] = Query(None, description="Comma-separated categories"),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    search: Optional[str] = Query(None, description="Filter panel search"),
    search_header: Optional[str] = Query(None, description="Header bar search"),
    from_entities: Optional[str] = Query(None, description="Comma-separated sender entity keys"),
    to_entities: Optional[str] = Query(None, description="Comma-separated recipient entity keys"),
    sort_field: str = Query("date", description="Sort field: date, time, name, amount, type, category"),
    sort_dir: str = Query("asc", description="Sort direction: asc or desc"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(100, ge=1, le=500, description="Results per page"),
    skip_aggregations: bool = Query(False, description="Skip aggregation queries for sort/page-only changes"),
):
    """Server-side paginated financial query with aggregations.

    Returns one page of transactions plus summary stats, entity flow data,
    volume-over-time, and category breakdown — all computed server-side.
    When skip_aggregations=True, only pagination queries run (summary, entity
    flow, charts, category breakdown return None — frontend uses cached values).
    """
    try:
        logger.info("[FinQuery] case_id=%s types=%s categories=%s page=%d page_size=%d sort=%s/%s",
                     case_id, types[:50] if types else None,
                     categories[:50] if categories else None,
                     page, page_size, sort_field, sort_dir)

        parsed_types = [t.strip() for t in types.split(",") if t.strip()] if types else None
        parsed_categories = [c.strip() for c in categories.split(",") if c.strip()] if categories else None
        parsed_from = [k.strip() for k in from_entities.split(",") if k.strip()] if from_entities else None
        parsed_to = [k.strip() for k in to_entities.split(",") if k.strip()] if to_entities else None

        offset = (page - 1) * page_size
        result = neo4j_service.query_financial_transactions(
            case_id=case_id,
            types=parsed_types,
            categories=parsed_categories,
            start_date=start_date,
            end_date=end_date,
            search=search.strip() if search else None,
            search_header=search_header.strip() if search_header else None,
            from_entity_keys=parsed_from,
            to_entity_keys=parsed_to,
            sort_field=sort_field,
            sort_dir=sort_dir,
            offset=offset,
            limit=page_size,
            skip_aggregations=skip_aggregations,
        )

        total = result["total"]
        total_pages = math.ceil(total / page_size) if total > 0 else 0

        logger.info("[FinQuery] Success: %d transactions, %d total, %d pages",
                     len(result.get("transactions", [])), total, total_pages)

        response = {
            **result,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

        # Return via JSONResponse with a safe serializer so Neo4j temporal/spatial
        # types don't crash Starlette's response handler (which produces a plain-text
        # 500 that bypasses our try/except).
        return JSONResponse(content=json.loads(json.dumps(response, default=str)))
    except Exception as e:
        logger.error("[FinQuery] Error: %s\n%s", str(e), traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/query-debug")
async def query_financial_debug(
    case_id: str = Query(..., description="REQUIRED: Case ID"),
):
    """Diagnostic endpoint to test each query phase individually."""
    phases = {}
    try:
        # Test summary query
        try:
            from services.neo4j_service import Neo4jService
            svc = neo4j_service
            svc._driver.session().close()  # Test connection
            phases["connection"] = "OK"
        except Exception as e:
            phases["connection"] = f"FAIL: {e}"

        try:
            result = neo4j_service.query_financial_transactions(
                case_id=case_id,
                sort_field="date",
                sort_dir="asc",
                offset=0,
                limit=5,
            )
            phases["query"] = "OK"
            phases["total"] = result.get("total", 0)
            phases["txn_count"] = len(result.get("transactions", []))
            phases["from_entities_count"] = len(result.get("from_entities", []))
            phases["to_entities_count"] = len(result.get("to_entities", []))
        except Exception as e:
            phases["query"] = f"FAIL: {type(e).__name__}: {e}"
            logger.error("[FinQueryDebug] %s\n%s", e, traceback.format_exc())

        return phases
    except Exception as e:
        logger.error("[FinQueryDebug] Outer error: %s\n%s", e, traceback.format_exc())
        return {"error": str(e)}


@router.get("/types")
async def get_transaction_types(
    case_id: str = Query(..., description="REQUIRED: Case ID"),
):
    """Return all distinct transaction types for a case."""
    try:
        types = neo4j_service.get_financial_transaction_types(case_id)
        return {"types": types}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities")
async def get_financial_entities(
    case_id: str = Query(..., description="REQUIRED: Case ID"),
):
    """Return all non-transaction entities in a case for from/to pickers."""
    try:
        entities = neo4j_service.get_financial_entities(case_id)
        return {"entities": entities}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_financial_summary(
    case_id: str = Query(..., description="REQUIRED: Case ID"),
    entity_key: Optional[str] = Query(None, description="Optional entity key for entity-relative inflow/outflow"),
):
    """
    Get aggregated financial summary statistics for a case.
    Without entity_key: returns overview metrics (total_volume, avg_amount, etc.)
    With entity_key: returns entity-relative inflows/outflows.
    """
    try:
        return neo4j_service.get_financial_summary(case_id=case_id, entity_key=entity_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/volume")
async def get_financial_volume(
    case_id: str = Query(..., description="REQUIRED: Case ID"),
):
    """
    Get transaction volume over time grouped by date and type for chart data.
    """
    try:
        data = neo4j_service.get_financial_volume_over_time(case_id=case_id)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/categorize/{node_key}")
async def categorize_transaction(node_key: str, body: CategorizeRequest):
    """
    Set the financial category on a transaction node.
    """
    try:
        result = neo4j_service.update_transaction_category(
            node_key=node_key,
            category=body.category,
            case_id=body.case_id,
        )
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Node not found"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/batch-categorize")
async def batch_categorize_transactions(body: BatchCategorizeRequest):
    """
    Set the financial category on multiple transaction nodes at once.
    """
    try:
        results = []
        for key in body.node_keys:
            result = neo4j_service.update_transaction_category(
                node_key=key,
                category=body.category,
                case_id=body.case_id,
            )
            results.append(result)
        success_count = sum(1 for r in results if r.get("success"))
        return {"success": True, "updated": success_count, "total": len(body.node_keys)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/from-to/{node_key}")
async def update_from_to(node_key: str, body: FromToRequest):
    """
    Set manual from/to entity override on a transaction node.
    """
    try:
        result = neo4j_service.update_transaction_from_to(
            node_key=node_key,
            case_id=body.case_id,
            from_key=body.from_key,
            from_name=body.from_name,
            to_key=body.to_key,
            to_name=body.to_name,
        )
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Node not found"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/details/{node_key}")
async def update_transaction_details(node_key: str, body: DetailsRequest):
    """
    Set purpose, counterparty_details, and/or notes on a transaction node.
    """
    try:
        result = neo4j_service.update_transaction_details(
            node_key=node_key,
            case_id=body.case_id,
            purpose=body.purpose,
            counterparty_details=body.counterparty_details,
            notes=body.notes,
        )
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Node not found"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/batch-from-to")
async def batch_update_from_to(body: BatchFromToRequest):
    """
    Set from/to entity on multiple transaction nodes at once.
    """
    try:
        result = neo4j_service.batch_update_from_to(
            node_keys=body.node_keys,
            case_id=body.case_id,
            from_key=body.from_key,
            from_name=body.from_name,
            to_key=body.to_key,
            to_name=body.to_name,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def get_categories(
    case_id: str = Query(..., description="REQUIRED: Case ID"),
):
    """
    Get predefined + custom financial categories found in a case.
    """
    try:
        categories = neo4j_service.get_financial_categories(case_id=case_id)
        return {"categories": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


PREDEFINED_CATEGORY_NAMES = {
    "Utility", "Payroll/Salary", "Rent/Lease", "Reimbursement",
    "Loan Payment", "Insurance", "Subscription", "Transfer",
    "Income", "Personal", "Legal/Professional", "Other",
}


@router.post("/categories")
async def create_category(body: CreateCategoryRequest):
    """
    Create a custom financial category for a case (persisted as a FinancialCategory node).
    """
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name cannot be empty")
    if name in PREDEFINED_CATEGORY_NAMES:
        raise HTTPException(status_code=400, detail=f"'{name}' is a predefined category and cannot be overridden")
    try:
        result = neo4j_service.create_financial_category(
            name=name,
            color=body.color,
            case_id=body.case_id,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to create category"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AutoExtractFromToRequest(BaseModel):
    case_id: str
    dry_run: bool = True


@router.post("/auto-extract-from-to")
async def auto_extract_from_to(body: AutoExtractFromToRequest):
    """
    Auto-extract sender/beneficiary from transaction fields using heuristics + LLM.

    With dry_run=true (default): returns proposals without applying.
    With dry_run=false: applies proposals and returns results.
    """
    try:
        from services.from_to_extraction_service import extract_from_to_for_case
        result = extract_from_to_for_case(
            case_id=body.case_id,
            dry_run=body.dry_run,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("message", "Extraction failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BulkCorrectionItem(BaseModel):
    name: str
    new_amount: float
    correction_reason: str


class BulkCorrectRequest(BaseModel):
    case_id: str
    corrections: List[BulkCorrectionItem]


class UpdateAmountRequest(BaseModel):
    case_id: str
    new_amount: float
    correction_reason: str


@router.put("/transactions/{node_key}/amount")
async def update_transaction_amount(node_key: str, body: UpdateAmountRequest):
    """Update a transaction amount with audit trail."""
    if body.new_amount == 0:
        raise HTTPException(status_code=400, detail="Amount cannot be zero")
    try:
        result = neo4j_service.update_transaction_amount(
            node_key=node_key,
            case_id=body.case_id,
            new_amount=body.new_amount,
            correction_reason=body.correction_reason,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transactions/bulk-correct")
async def bulk_correct_transactions(body: BulkCorrectRequest):
    """Apply amount corrections in bulk, matching by transaction name."""
    if not body.corrections:
        raise HTTPException(status_code=400, detail="No corrections provided")
    try:
        # Fetch all transactions for this case to match by name
        all_txns = neo4j_service.get_financial_transactions(case_id=body.case_id)

        # Build a lookup: lowercase name -> list of transaction dicts
        name_lookup: dict = {}
        for t in all_txns:
            name = (t.get("name") or "").strip().lower()
            if name:
                name_lookup.setdefault(name, []).append(t)

        results = []
        for correction in body.corrections:
            search_name = correction.name.strip().lower()
            if not search_name:
                results.append({"name": correction.name, "status": "skipped", "reason": "Empty name"})
                continue

            matches = name_lookup.get(search_name)
            if not matches:
                results.append({"name": correction.name, "status": "not_found", "reason": "No matching transaction"})
                continue

            if correction.new_amount == 0:
                results.append({"name": correction.name, "status": "skipped", "reason": "Amount cannot be zero"})
                continue

            for match in matches:
                try:
                    neo4j_service.update_transaction_amount(
                        node_key=match["key"],
                        case_id=body.case_id,
                        new_amount=correction.new_amount,
                        correction_reason=correction.correction_reason,
                    )
                    results.append({
                        "name": correction.name,
                        "key": match["key"],
                        "status": "corrected",
                        "old_amount": match.get("amount"),
                        "new_amount": correction.new_amount,
                    })
                except Exception as exc:
                    results.append({
                        "name": correction.name,
                        "key": match["key"],
                        "status": "error",
                        "reason": str(exc),
                    })

        corrected = sum(1 for r in results if r["status"] == "corrected")
        not_found = sum(1 for r in results if r["status"] == "not_found")
        errors = sum(1 for r in results if r["status"] == "error")
        return {
            "success": True,
            "corrected": corrected,
            "not_found": not_found,
            "errors": errors,
            "total": len(body.corrections),
            "results": results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class LinkSubTransactionRequest(BaseModel):
    case_id: str
    child_key: str


@router.post("/transactions/{parent_key}/sub-transactions")
async def link_sub_transaction(parent_key: str, body: LinkSubTransactionRequest):
    """Link a child transaction to a parent."""
    if parent_key == body.child_key:
        raise HTTPException(status_code=400, detail="Cannot link a transaction to itself")
    try:
        result = neo4j_service.link_sub_transaction(parent_key, body.child_key, body.case_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/transactions/{child_key}/parent")
async def unlink_sub_transaction(
    child_key: str,
    case_id: str = Query(..., description="REQUIRED: Case ID"),
):
    """Remove a child transaction from its parent group."""
    try:
        result = neo4j_service.unlink_sub_transaction(child_key, case_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transactions/{parent_key}/sub-transactions")
async def get_transaction_children(
    parent_key: str,
    case_id: str = Query(..., description="REQUIRED: Case ID"),
):
    """Get all child sub-transactions for a parent."""
    try:
        children = neo4j_service.get_transaction_children(parent_key, case_id)
        return {"children": children, "count": len(children)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/pdf")
async def export_financial_pdf(
    case_id: str = Query(..., description="REQUIRED: Case ID"),
    case_name: str = Query("Case", description="Case name for the header"),
    categories: Optional[str] = Query(None, description="Comma-separated categories to filter"),
    types: Optional[str] = Query(None, description="Comma-separated transaction types to filter"),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    from_entities: Optional[str] = Query(None, description="Comma-separated sender entity keys"),
    to_entities: Optional[str] = Query(None, description="Comma-separated recipient entity keys"),
    entity_key: Optional[str] = Query(None, description="Filter by entity key (from/to) — legacy single"),
    entity_name: Optional[str] = Query(None, description="Entity name for filter display"),
    entity: Optional[str] = Query(None, description="Entity name to filter by from/to (legacy)"),
    search: Optional[str] = Query(None, description="Filter panel search"),
    search_header: Optional[str] = Query(None, description="Header bar search"),
    include_entity_notes: bool = Query(True, description="Include entity notes appendix"),
):
    """Export filtered financial transactions as a PDF report.

    Reuses query_financial_transactions() so filtering is identical to the UI.
    """
    from math import fabs

    try:
        # Parse filter params
        parsed_types = [t.strip() for t in types.split(",") if t.strip()] if types else None
        parsed_categories = [c.strip() for c in categories.split(",") if c.strip()] if categories else None
        parsed_from = [k.strip() for k in from_entities.split(",") if k.strip()] if from_entities else None
        parsed_to = [k.strip() for k in to_entities.split(",") if k.strip()] if to_entities else None

        # Legacy single-entity filter → map to from/to entity filters
        if not parsed_from and not parsed_to:
            if entity_key:
                parsed_from = [entity_key]
                parsed_to = [entity_key]
            elif entity:
                parsed_from = [entity]
                parsed_to = [entity]

        # Use shared query with large limit to get all matching transactions
        qr = neo4j_service.query_financial_transactions(
            case_id=case_id,
            types=parsed_types,
            categories=parsed_categories,
            start_date=start_date,
            end_date=end_date,
            search=search.strip() if search else None,
            search_header=search_header.strip() if search_header else None,
            from_entity_keys=parsed_from,
            to_entity_keys=parsed_to,
            sort_field="date",
            sort_dir="asc",
            offset=0,
            limit=999999,
        )

        transactions = qr["transactions"]
        from_entities_list = [
            {"name": e["name"], "count": e["count"], "total": e["totalAmount"]}
            for e in qr["from_entities"]
        ]
        to_entities_list = [
            {"name": e["name"], "count": e["count"], "total": e["totalAmount"]}
            for e in qr["to_entities"]
        ]

        # Build filters description for header
        filters = []
        if parsed_categories:
            filters.append(f"Categories: {', '.join(parsed_categories)}")
        if parsed_types:
            filters.append(f"Types: {', '.join(parsed_types)}")
        if start_date:
            filters.append(f"From: {start_date}")
        if end_date:
            filters.append(f"To: {end_date}")
        if search:
            filters.append(f'Search: "{search.strip()}"')
        if search_header:
            filters.append(f'Search: "{search_header.strip()}"')
        if from_entities:
            filters.append(f"Senders: {len(parsed_from)} selected")
        if to_entities:
            filters.append(f"Recipients: {len(parsed_to)} selected")
        filters_description = " | ".join(filters) if filters else ""

        # Category breakdown from server
        category_counts = {cat: data["count"] for cat, data in qr["category_breakdown"].items()}
        category_amounts = {cat: data["amount"] for cat, data in qr["category_breakdown"].items()}

        # Volume timeline from server data
        volume_by_month = {}
        for v in qr["volume_data"]:
            d = v.get("date")
            if not d:
                continue
            month_key = d[:7]
            volume_by_month[month_key] = volume_by_month.get(month_key, 0.0) + (v.get("total_amount") or 0)
        volume_timeline = sorted(volume_by_month.items())

        # Entity notes appendix
        entity_notes = None
        if include_entity_notes:
            try:
                entity_keys = set()
                for t in transactions:
                    if isinstance(t.get("from_entity"), dict) and t["from_entity"].get("key"):
                        entity_keys.add(t["from_entity"]["key"])
                    if isinstance(t.get("to_entity"), dict) and t["to_entity"].get("key"):
                        entity_keys.add(t["to_entity"]["key"])

                if entity_keys:
                    entity_notes = []
                    with neo4j_service._driver.session() as session:
                        result = session.run(
                            """
                            MATCH (n {case_id: $case_id})
                            WHERE n.key IN $keys AND NOT n:Document
                            RETURN n.key AS key, n.name AS name,
                                   labels(n)[0] AS type,
                                   n.notes AS notes, n.summary AS summary
                            """,
                            case_id=case_id,
                            keys=list(entity_keys),
                        )
                        for record in result:
                            r = dict(record)
                            if r.get("notes") or r.get("summary"):
                                entity_notes.append(r)
                    entity_notes.sort(key=lambda e: (e.get("name") or "").lower())
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to fetch entity notes: {e}")

        # Compute directional inflow/outflow
        from_keys_set = set(parsed_from) if parsed_from else None
        to_keys_set = set(parsed_to) if parsed_to else None
        has_entity_selection = bool(from_keys_set or to_keys_set)
        total_inflows = 0.0
        total_outflows = 0.0
        inflow_by_entity = {}
        outflow_by_entity = {}

        def _entity_key(e):
            if isinstance(e, dict):
                return e.get("key") or e.get("name")
            return None

        def _entity_name(e):
            if isinstance(e, dict):
                return e.get("name") or e.get("key")
            return None

        def _add_to_map(m, key, name, amt):
            if key not in m:
                m[key] = {"name": name or key, "amount": 0.0}
            m[key]["amount"] += amt

        if has_entity_selection:
            for t in transactions:
                amt = fabs(float(t.get("amount") or 0))
                tk = _entity_key(t.get("to_entity"))
                tn = _entity_name(t.get("to_entity"))
                fk = _entity_key(t.get("from_entity"))
                fn = _entity_name(t.get("from_entity"))
                if from_keys_set:
                    if fk and fk in from_keys_set:
                        total_outflows += amt
                        if tn:
                            _add_to_map(outflow_by_entity, tk or tn, tn, amt)
                    if tk and tk in from_keys_set:
                        total_inflows += amt
                        if fn:
                            _add_to_map(inflow_by_entity, fk or fn, fn, amt)
                elif to_keys_set:
                    if tk and tk in to_keys_set:
                        total_inflows += amt
                        if fn:
                            _add_to_map(inflow_by_entity, fk or fn, fn, amt)
                    if fk and fk in to_keys_set:
                        total_outflows += amt
                        if tn:
                            _add_to_map(outflow_by_entity, tk or tn, tn, amt)
        else:
            for t in transactions:
                raw = float(t.get("amount") or 0)
                amt = fabs(raw)
                if raw >= 0:
                    total_outflows += amt
                else:
                    total_inflows += amt

        inflow_entities_list = sorted(inflow_by_entity.values(), key=lambda e: e["amount"], reverse=True)
        outflow_entities_list = sorted(outflow_by_entity.values(), key=lambda e: e["amount"], reverse=True)

        # Group sub-transactions under their parents for adjacent display
        parent_children = {}
        top_level = []
        txn_by_key = {t["key"]: t for t in transactions}
        for t in transactions:
            ptk = t.get("parent_transaction_key")
            if ptk and ptk in txn_by_key:
                parent_children.setdefault(ptk, []).append(t)
            else:
                top_level.append(t)
        grouped_transactions = []
        for t in top_level:
            grouped_transactions.append(t)
            for child in parent_children.get(t["key"], []):
                grouped_transactions.append(child)
        transactions = grouped_transactions

        html = generate_financial_pdf(
            transactions,
            case_name,
            filters_description,
            entity_notes=entity_notes,
            from_entities=from_entities_list,
            to_entities=to_entities_list,
            selected_from_keys=from_keys_set,
            selected_to_keys=to_keys_set,
            category_counts=category_counts,
            category_amounts=category_amounts,
            volume_timeline=volume_timeline,
            has_entity_selection=has_entity_selection,
            total_inflows=total_inflows,
            total_outflows=total_outflows,
            inflow_entities=inflow_entities_list if has_entity_selection else None,
            outflow_entities=outflow_entities_list if has_entity_selection else None,
        )

        return Response(content=html, media_type="text/html")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-notes")
async def upload_notes_csv(
    case_id: str = Form(..., description="REQUIRED: Case ID"),
    file: UploadFile = File(..., description="CSV file with ref_id and notes columns"),
):
    """Upload investigator notes as CSV, matched to transactions by ref_id.

    CSV columns: ref_id (required), notes, interviewer, date, question, answer (optional).
    Returns matched count and list of unmatched ref_ids.
    """
    import csv
    import io

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # Handle Excel BOM
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded CSV")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file has no headers")

    # Normalize header names for flexible matching
    norm = {h.strip().lower(): h for h in reader.fieldnames}
    ref_col = norm.get("ref_id") or norm.get("ref")
    if not ref_col:
        raise HTTPException(status_code=400, detail="CSV must have a 'ref_id' or 'ref' column")

    notes_col = norm.get("notes") or norm.get("note")
    interviewer_col = norm.get("interviewer")
    date_col = norm.get("date")
    question_col = norm.get("question") or norm.get("q")
    answer_col = norm.get("answer") or norm.get("a")

    notes_data = []
    for row in reader:
        entry = {"ref_id": (row.get(ref_col) or "").strip()}
        if notes_col:
            entry["notes"] = (row.get(notes_col) or "").strip()
        if interviewer_col:
            entry["interviewer"] = (row.get(interviewer_col) or "").strip()
        if date_col:
            entry["date"] = (row.get(date_col) or "").strip()
        if question_col:
            entry["question"] = (row.get(question_col) or "").strip()
        if answer_col:
            entry["answer"] = (row.get(answer_col) or "").strip()
        if entry["ref_id"]:
            notes_data.append(entry)

    if not notes_data:
        raise HTTPException(status_code=400, detail="No valid rows found in CSV")

    try:
        result = neo4j_service.bulk_append_notes_by_ref_id(case_id, notes_data)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
