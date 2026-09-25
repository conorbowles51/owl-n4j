import type { StatementDraft } from "./statement-review-draft"
import { serverStatementDraft } from "./statement-review-draft"

// Compare every editable value, normalizing only optional transport defaults.
// A saved balance must not make newer date, party or amount edits look saved.
export function statementRowSnapshot(row: StatementDraft["rows"][number]) {
  return JSON.stringify({
    id: row.id,
    excluded: row.excluded,
    manual_page: row.manual_page ?? null,
    source_order_anchor: row.source_order_anchor
      ? {
          relation: row.source_order_anchor.relation,
          row_id: row.source_order_anchor.row_id,
        }
      : null,
    counterparty_link: row.counterparty_link
      ? { kind: row.counterparty_link.kind, id: row.counterparty_link.id }
      : null,
    date_unprinted: !!row.date_unprinted,
    date: row.date,
    direction: row.direction || "",
    date_values: Object.fromEntries(
      Object.entries(row.date_values || {}).sort()
    ),
    description: row.description,
    counterparty: row.counterparty,
    amount_minor: row.amount_minor,
    balance_minor: row.balance_minor,
    reason: row.reason,
  })
}

// The API supplies defaults and can serialize keys in a different order. Compare
// the declared review values, not transport JSON bytes, before acknowledging it.
export function statementReviewSnapshot(request: Record<string, unknown>) {
  const draft = serverStatementDraft(request)
  if (!draft) return null
  return JSON.stringify({
    ...draft,
    rows: draft.rows.map(statementRowSnapshot),
    statement_id: request.statement_id ?? null,
    currency: request.currency ?? "",
    replaces_source_document_id: request.replaces_source_document_id ?? null,
    replacement_revision: request.replacement_revision ?? null,
  })
}
