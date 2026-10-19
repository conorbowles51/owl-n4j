"""Keep bounded ledger pages intact when sending tool evidence to the model."""

from services.agent.json_utils import to_jsonable, truncate_payload

FINANCIAL_LEDGER_TOOLS = frozenset({
    "get_financial_transactions", "analyze_financial_transactions", "get_financial_coverage",
})


def tool_data_for_model(name, data):
    # Ledger tools enforce their own page and full-population limits. Applying
    # the generic recursive 20-item preview here would skip unseen payments on
    # the next page and could remove totals, exclusions or pagination metadata.
    if name in FINANCIAL_LEDGER_TOOLS:
        return to_jsonable(data)
    return truncate_payload(data, max_items=20, max_text_chars=1500)
