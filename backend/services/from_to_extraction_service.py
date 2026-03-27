"""
From/To + Category Extraction Service — auto-extracts sender/beneficiary and
financial category from transaction fields.

Two-phase approach:
1. Heuristic pass — regex on `name` field for from/to (free, instant)
2. LLM pass — batched GPT-4o-mini calls for from/to + category
Then matches extracted names against existing graph entities.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from services.llm_service import LLMService
from services.neo4j_service import neo4j_service


# ---------------------------------------------------------------------------
# Valid categories for LLM proposals (excludes "Uncategorized")
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {
    "Utility", "Payroll/Salary", "Rent/Lease", "Reimbursement",
    "Loan Payment", "Insurance", "Subscription", "Transfer",
    "Income", "Personal", "Legal/Professional", "Other",
}


# ---------------------------------------------------------------------------
# Phase 1: Heuristic extraction from transaction name (from/to only)
# ---------------------------------------------------------------------------

# Patterns: "Payment to X", "Transfer from X to Y", "X - Mar 15", etc.
_HEURISTIC_PATTERNS = [
    # "Transfer from X to Y"
    re.compile(
        r"(?:transfer|wire|sent?)\s+from\s+(?P<from>.+?)\s+to\s+(?P<to>.+?)(?:\s*[-–—]\s*|\s*$)",
        re.IGNORECASE,
    ),
    # "Payment from X to Y"
    re.compile(
        r"(?:payment|deposit|remittance)\s+from\s+(?P<from>.+?)\s+to\s+(?P<to>.+?)(?:\s*[-–—]\s*|\s*$)",
        re.IGNORECASE,
    ),
    # "Payment to X" (no from)
    re.compile(
        r"(?:payment|transfer|wire|sent?|disbursement|remittance)\s+to\s+(?P<to>.+?)(?:\s*[-–—]\s*|\s*$)",
        re.IGNORECASE,
    ),
    # "Payment from X" (no to)
    re.compile(
        r"(?:payment|transfer|wire|receipt|deposit|remittance)\s+from\s+(?P<from>.+?)(?:\s*[-–—]\s*|\s*$)",
        re.IGNORECASE,
    ),
    # "Received from X"
    re.compile(
        r"received\s+from\s+(?P<from>.+?)(?:\s*[-–—]\s*|\s*$)",
        re.IGNORECASE,
    ),
    # "Invoice to X"
    re.compile(
        r"invoice\s+to\s+(?P<to>.+?)(?:\s*[-–—]\s*|\s*$)",
        re.IGNORECASE,
    ),
    # "X paid Y" / "X paid to Y"
    re.compile(
        r"^(?P<from>.+?)\s+paid\s+(?:to\s+)?(?P<to>.+?)(?:\s*[-–—]\s*|\s*$)",
        re.IGNORECASE,
    ),
]


def _clean_extracted_name(name: str) -> Optional[str]:
    """Clean up an extracted entity name, return None if useless."""
    if not name:
        return None
    # Strip trailing date-like patterns, amounts, etc.
    cleaned = re.sub(r"\s*[-–—]\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b.*$", "", name, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[-–—]\s*\d{1,2}/\d{1,2}.*$", "", cleaned)
    cleaned = re.sub(r"\s*[-–—]\s*\d{4}.*$", "", cleaned)
    cleaned = re.sub(r"\s*\$[\d,.]+.*$", "", cleaned)
    cleaned = cleaned.strip(" -–—,.")
    if len(cleaned) < 2 or cleaned.lower() in ("n/a", "unknown", "none", "null", "various"):
        return None
    return cleaned


def extract_heuristic(name: str) -> Dict[str, Optional[str]]:
    """
    Try to extract from/to entity names from a transaction name using regex.

    Returns: {"from_name": str|None, "to_name": str|None}
    """
    if not name:
        return {"from_name": None, "to_name": None}

    for pattern in _HEURISTIC_PATTERNS:
        m = pattern.search(name)
        if m:
            groups = m.groupdict()
            from_name = _clean_extracted_name(groups.get("from", ""))
            to_name = _clean_extracted_name(groups.get("to", ""))
            if from_name or to_name:
                return {"from_name": from_name, "to_name": to_name}

    return {"from_name": None, "to_name": None}


# ---------------------------------------------------------------------------
# Phase 2: LLM extraction (from/to + category)
# ---------------------------------------------------------------------------

_CATEGORY_LIST_STR = ", ".join(sorted(VALID_CATEGORIES))

FROM_TO_EXTRACTION_PROMPT = f"""You are a financial transaction analyst. Given a batch of financial transactions, extract the sender (from), beneficiary (to), and financial category for each transaction.

For each transaction, analyze the name, summary, counterparty details, and purpose to determine:
- **from**: Who sent/paid the money (the sender, payer, or originator)
- **to**: Who received the money (the beneficiary, payee, or recipient)
- **category**: The most appropriate financial category from ONLY this list: {_CATEGORY_LIST_STR}

Rules:
1. Use the transaction name and summary as primary sources.
2. The existing financial_category (if shown) can help with from/to: "Payroll/Salary" means the 'to' is likely an employee; "Rent/Lease" means the 'to' is likely a landlord/property company.
3. Return proper names (person or company names) for from/to, not descriptions like "unknown" or "recipient".
4. If you genuinely cannot determine a party, use null for that field.
5. Be precise — extract the actual entity name, not a paraphrase.
6. For category, choose the single best match from the allowed list. If none fits well, use "Other". Never return "Uncategorized".

Return ONLY a JSON object with this structure:
{{
  "extractions": [
    {{"index": 0, "from": "Entity Name" or null, "to": "Entity Name" or null, "category": "Category Name"}},
    {{"index": 1, "from": "Entity Name" or null, "to": "Entity Name" or null, "category": "Category Name"}}
  ]
}}

TRANSACTIONS:
"""

BATCH_SIZE = 50
MAX_LLM_TRANSACTIONS = 2000     # Cap to avoid extreme runtimes
LLM_CONCURRENCY = 6             # Parallel LLM API calls


def _format_transaction_for_llm(idx: int, txn: Dict) -> str:
    """Format a single transaction for the LLM prompt."""
    parts = [f"[{idx}]"]
    if txn.get("name"):
        parts.append(f"Name: {txn['name']}")
    if txn.get("summary"):
        parts.append(f"Summary: {txn['summary']}")
    if txn.get("counterparty_details"):
        parts.append(f"Counterparty: {txn['counterparty_details']}")
    if txn.get("purpose"):
        parts.append(f"Purpose: {txn['purpose']}")
    if txn.get("category") and txn["category"] != "Uncategorized":
        parts.append(f"Category: {txn['category']}")
    return " | ".join(parts)


def _process_single_batch(batch_start: int, batch: List[Dict], llm: LLMService) -> List[Dict]:
    """Process a single LLM batch. Thread-safe: creates its own LLMService."""
    lines = []
    for i, txn in enumerate(batch):
        lines.append(_format_transaction_for_llm(i, txn))

    prompt = FROM_TO_EXTRACTION_PROMPT + "\n".join(lines)

    # Each thread uses its own LLMService instance for thread safety
    thread_llm = LLMService()
    thread_llm.set_config("openai", "gpt-4o-mini")

    try:
        raw = thread_llm.call(prompt, temperature=0.1, json_mode=True, timeout=120)
    except Exception as e:
        print(f"[FromToExtract] LLM batch at {batch_start} failed: {e}")
        return []

    results = []
    try:
        parsed = json.loads(raw)
        extractions = parsed.get("extractions", [])
        for ext in extractions:
            abs_index = batch_start + ext.get("index", 0)
            results.append({
                "index": abs_index,
                "from": ext.get("from"),
                "to": ext.get("to"),
                "category": ext.get("category"),
            })
    except json.JSONDecodeError:
        print(f"[FromToExtract] Failed to parse LLM response for batch starting at {batch_start}")

    return results


def extract_from_to_llm(transactions: List[Dict], llm: LLMService) -> List[Dict]:
    """
    Use GPT-4o-mini to extract from/to and category for transactions.
    Processes batches concurrently using ThreadPoolExecutor.

    Args:
        transactions: List of transaction dicts (must have sequential indices)
        llm: LLMService instance (used for config reference only)

    Returns:
        List of {"index": int, "from": str|None, "to": str|None, "category": str|None}
    """
    if not transactions:
        return []

    # Build batch list
    batches = []
    for batch_start in range(0, len(transactions), BATCH_SIZE):
        batch = transactions[batch_start:batch_start + BATCH_SIZE]
        batches.append((batch_start, batch))

    total_batches = len(batches)
    print(f"[FromToExtract] Processing {len(transactions)} transactions in {total_batches} batches "
          f"({LLM_CONCURRENCY} concurrent)")

    all_results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=LLM_CONCURRENCY) as executor:
        futures = {
            executor.submit(_process_single_batch, bs, b, llm): bs
            for bs, b in batches
        }

        for future in as_completed(futures):
            batch_start = futures[future]
            try:
                results = future.result()
                all_results.extend(results)
            except Exception as e:
                print(f"[FromToExtract] Batch at {batch_start} raised exception: {e}")

            completed += 1
            if completed % 5 == 0 or completed == total_batches:
                print(f"[FromToExtract] Progress: {completed}/{total_batches} batches complete")

    return all_results


# ---------------------------------------------------------------------------
# Entity matching
# ---------------------------------------------------------------------------

def _normalize_for_match(name: str) -> str:
    """Normalize a name for matching against entities."""
    return re.sub(r"[^a-z0-9\s]", "", name.lower()).strip()


def match_to_entity(
    extracted_name: Optional[str],
    entity_index: Dict[str, Dict],
    entity_key_index: Dict[str, Dict],
) -> Dict:
    """
    Match an extracted name against existing graph entities.

    Returns: {"key": str|None, "name": str, "matched": bool}
    """
    if not extracted_name:
        return {"key": None, "name": None, "matched": False}

    norm = _normalize_for_match(extracted_name)
    if not norm:
        return {"key": None, "name": extracted_name, "matched": False}

    # Exact normalized name match
    if norm in entity_index:
        ent = entity_index[norm]
        return {"key": ent["key"], "name": ent["name"], "matched": True}

    # Exact key match (e.g., "john-smith")
    key_form = norm.replace(" ", "-")
    if key_form in entity_key_index:
        ent = entity_key_index[key_form]
        return {"key": ent["key"], "name": ent["name"], "matched": True}

    # Substring matching: entity name contains extracted name or vice versa
    for ent_norm, ent in entity_index.items():
        if len(norm) >= 3 and (norm in ent_norm or ent_norm in norm):
            return {"key": ent["key"], "name": ent["name"], "matched": True}

    # No match — return as custom name
    return {"key": None, "name": extracted_name, "matched": False}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def extract_from_to_for_case(
    case_id: str,
    dry_run: bool = True,
) -> Dict:
    """
    Full extraction pipeline for a case: from/to + category.

    1. Fetch transactions that need from/to OR category
    2. Phase 1: heuristic from/to extraction
    3. Phase 2: LLM extraction for from/to + category
    4. Match from/to against existing entities
    5. If not dry_run, write to Neo4j

    Returns summary with proposals.
    """
    print(f"[FromToExtract] Starting extraction for case {case_id} (dry_run={dry_run})")

    # ---- Step 1: Fetch all transactions ----
    all_transactions = neo4j_service.get_financial_transactions(case_id=case_id)
    if not all_transactions:
        return {"success": True, "message": "No transactions found", "total": 0, "proposals": []}

    # A transaction is eligible if it needs from/to OR needs a category
    eligible = []
    for t in all_transactions:
        needs_from_to = not (t.get("has_manual_from") and t.get("has_manual_to"))
        needs_category = t.get("category", "Uncategorized") == "Uncategorized"
        if needs_from_to or needs_category:
            t["_needs_from_to"] = needs_from_to
            t["_needs_category"] = needs_category
            eligible.append(t)

    print(f"[FromToExtract] {len(all_transactions)} total, {len(eligible)} eligible for extraction")

    if not eligible:
        return {
            "success": True,
            "message": "All transactions already have manual from/to and categories",
            "total": len(all_transactions),
            "eligible": 0,
            "proposals": [],
        }

    # ---- Step 2: Build entity index ----
    entities = neo4j_service.get_financial_entities(case_id)
    entity_name_index: Dict[str, Dict] = {}
    entity_key_index: Dict[str, Dict] = {}
    for ent in entities:
        name = ent.get("name", "")
        key = ent.get("key", "")
        if name:
            entity_name_index[_normalize_for_match(name)] = ent
        if key:
            entity_key_index[key.lower()] = ent

    print(f"[FromToExtract] {len(entities)} entities available for matching")

    # ---- Step 3: Heuristic from/to extraction ----
    proposals = []
    needs_llm = []
    heuristic_from_to: Dict[str, Dict] = {}  # txn_key -> {from, to}

    for txn in eligible:
        needs_ft = txn["_needs_from_to"]
        needs_cat = txn["_needs_category"]
        has_from_already = txn.get("has_manual_from", False)
        has_to_already = txn.get("has_manual_to", False)

        # Heuristic only extracts from/to
        result = extract_heuristic(txn.get("name", ""))
        proposed_from = result["from_name"] if (needs_ft and not has_from_already) else None
        proposed_to = result["to_name"] if (needs_ft and not has_to_already) else None
        got_heuristic_hit = proposed_from or proposed_to

        if got_heuristic_hit:
            heuristic_from_to[txn["key"]] = {"from": proposed_from, "to": proposed_to}

        # Send to LLM if: needs category, OR (needs from/to and no heuristic hit)
        if needs_cat or (needs_ft and not got_heuristic_hit):
            needs_llm.append(txn)
        elif got_heuristic_hit:
            # Pure heuristic from/to, no category needed
            proposals.append({
                "txn_key": txn["key"],
                "txn_name": txn.get("name", ""),
                "source": "heuristic",
                "proposed_from": proposed_from,
                "proposed_to": proposed_to,
                "proposed_category": None,
                "needs_from": not has_from_already,
                "needs_to": not has_to_already,
                "needs_category": False,
            })

    print(f"[FromToExtract] Heuristic: {len(proposals)} pure-heuristic proposals, {len(needs_llm)} need LLM")

    # ---- Step 4: LLM extraction ----
    if len(needs_llm) > MAX_LLM_TRANSACTIONS:
        print(f"[FromToExtract] Capping LLM batch from {len(needs_llm)} to {MAX_LLM_TRANSACTIONS}")
        needs_llm = needs_llm[:MAX_LLM_TRANSACTIONS]

    if needs_llm:
        llm = LLMService()
        llm.set_cost_tracking_context(
            case_id=case_id,
            job_type="ingestion",
            description="Auto-extract from/to entities and categories from transactions",
        )

        llm_results = extract_from_to_llm(needs_llm, llm)
        llm.clear_cost_tracking_context()

        # Map results back to transactions
        for ext in llm_results:
            idx = ext["index"]
            if idx >= len(needs_llm):
                continue
            txn = needs_llm[idx]
            has_from_already = txn.get("has_manual_from", False)
            has_to_already = txn.get("has_manual_to", False)
            needs_ft = txn["_needs_from_to"]
            needs_cat = txn["_needs_category"]

            # From/to: prefer heuristic if available, else use LLM
            h_hit = heuristic_from_to.get(txn["key"])
            if h_hit and needs_ft:
                proposed_from = h_hit["from"] if not has_from_already else None
                proposed_to = h_hit["to"] if not has_to_already else None
                ft_source = "heuristic"
            elif needs_ft:
                proposed_from = ext.get("from") if not has_from_already else None
                proposed_to = ext.get("to") if not has_to_already else None
                ft_source = "llm"
            else:
                proposed_from = None
                proposed_to = None
                ft_source = "llm"

            # Category from LLM (validated)
            proposed_category = ext.get("category") if needs_cat else None
            if proposed_category and proposed_category not in VALID_CATEGORIES:
                proposed_category = None

            if proposed_from or proposed_to or proposed_category:
                proposals.append({
                    "txn_key": txn["key"],
                    "txn_name": txn.get("name", ""),
                    "source": ft_source if (proposed_from or proposed_to) else "llm",
                    "proposed_from": proposed_from,
                    "proposed_to": proposed_to,
                    "proposed_category": proposed_category,
                    "needs_from": not has_from_already,
                    "needs_to": not has_to_already,
                    "needs_category": needs_cat,
                })

        print(f"[FromToExtract] LLM pass complete, {len(proposals)} total proposals")

    # ---- Step 5: Entity matching (from/to only) ----
    entity_matches = 0
    custom_names = 0

    for proposal in proposals:
        if proposal["proposed_from"]:
            match = match_to_entity(proposal["proposed_from"], entity_name_index, entity_key_index)
            proposal["from_entity"] = match
            if match["matched"]:
                entity_matches += 1
            elif match["name"]:
                custom_names += 1

        if proposal["proposed_to"]:
            match = match_to_entity(proposal["proposed_to"], entity_name_index, entity_key_index)
            proposal["to_entity"] = match
            if match["matched"]:
                entity_matches += 1
            elif match["name"]:
                custom_names += 1

    print(f"[FromToExtract] Matching: {entity_matches} entity matches, {custom_names} custom names")

    # ---- Step 6: Apply if not dry_run ----
    applied = 0
    categories_applied = 0
    if not dry_run:
        for proposal in proposals:
            # Apply from/to
            from_key = None
            from_name = None
            to_key = None
            to_name = None

            if proposal.get("from_entity") and proposal["needs_from"]:
                from_key = proposal["from_entity"]["key"]  # may be None for custom
                from_name = proposal["from_entity"]["name"]

            if proposal.get("to_entity") and proposal["needs_to"]:
                to_key = proposal["to_entity"]["key"]  # may be None for custom
                to_name = proposal["to_entity"]["name"]

            if from_name or to_name:
                try:
                    result = neo4j_service.update_transaction_from_to(
                        node_key=proposal["txn_key"],
                        case_id=case_id,
                        from_key=from_key,
                        from_name=from_name,
                        to_key=to_key,
                        to_name=to_name,
                    )
                    if result.get("success"):
                        applied += 1
                except Exception as e:
                    print(f"[FromToExtract] Failed to update from/to for {proposal['txn_key']}: {e}")

            # Apply category
            if proposal.get("proposed_category") and proposal.get("needs_category"):
                try:
                    neo4j_service.update_transaction_category(
                        node_key=proposal["txn_key"],
                        category=proposal["proposed_category"],
                        case_id=case_id,
                    )
                    categories_applied += 1
                except Exception as e:
                    print(f"[FromToExtract] Failed to update category for {proposal['txn_key']}: {e}")

        print(f"[FromToExtract] Applied {applied} from/to updates, {categories_applied} category updates")

    heuristic_count = sum(1 for p in proposals if p["source"] == "heuristic")
    llm_count = sum(1 for p in proposals if p["source"] == "llm")
    category_proposals_count = sum(1 for p in proposals if p.get("proposed_category"))

    summary = {
        "success": True,
        "total": len(all_transactions),
        "eligible": len(eligible),
        "proposals_count": len(proposals),
        "heuristic_count": heuristic_count,
        "llm_count": llm_count,
        "entity_matches": entity_matches,
        "custom_names": custom_names,
        "category_proposals_count": category_proposals_count,
        "applied": applied if not dry_run else 0,
        "categories_applied": categories_applied if not dry_run else 0,
        "dry_run": dry_run,
        "proposals": [
            {
                "txn_key": p["txn_key"],
                "txn_name": p["txn_name"],
                "source": p["source"],
                "from": p.get("from_entity", {}).get("name") if p.get("from_entity") else None,
                "from_key": p.get("from_entity", {}).get("key") if p.get("from_entity") else None,
                "from_matched": p.get("from_entity", {}).get("matched", False) if p.get("from_entity") else False,
                "to": p.get("to_entity", {}).get("name") if p.get("to_entity") else None,
                "to_key": p.get("to_entity", {}).get("key") if p.get("to_entity") else None,
                "to_matched": p.get("to_entity", {}).get("matched", False) if p.get("to_entity") else False,
                "proposed_category": p.get("proposed_category"),
            }
            for p in proposals
        ],
    }

    print(f"[FromToExtract] Complete: {json.dumps({k: v for k, v in summary.items() if k != 'proposals'}, indent=2)}")
    return summary
