"""
Financial Router - endpoints for financial analysis and transaction visualization.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from services import neo4j_service
from services.financial_export_service import generate_financial_pdf

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


class UpdateAmountRequest(BaseModel):
    case_id: str
    new_amount: float
    correction_reason: str


@router.put("/transactions/{node_key}/amount")
async def update_transaction_amount(node_key: str, body: UpdateAmountRequest):
    """Update a transaction amount with audit trail."""
    if body.new_amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")
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
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
):
    """Export filtered financial transactions as a PDF report."""
    try:
        result = neo4j_service.get_financial_transactions(case_id=case_id)
        transactions = result.get("transactions", []) if isinstance(result, dict) else result

        filters = []
        if categories:
            cat_list = [c.strip() for c in categories.split(",")]
            transactions = [t for t in transactions if t.get("financial_category") in cat_list]
            filters.append(f"Categories: {', '.join(cat_list)}")
        if start_date:
            transactions = [t for t in transactions if t.get("date") and t["date"] >= start_date]
            filters.append(f"From: {start_date}")
        if end_date:
            transactions = [t for t in transactions if t.get("date") and t["date"] <= end_date]
            filters.append(f"To: {end_date}")

        filters_description = " | ".join(filters) if filters else ""

        pdf_bytes = generate_financial_pdf(transactions, case_name, filters_description)

        safe_name = case_name.replace(" ", "_").replace("/", "-")[:50]
        filename = f"Financial_Report_{safe_name}_{datetime.now().strftime('%Y%m%d')}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
