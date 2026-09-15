import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import {
  financialDraftKey,
  useFinancialDraftStore,
} from "../stores/financial-drafts"

export const emptyPaymentTableView = {
  search: "",
  currency: "",
  minimum: "",
  maximum: "",
  direction: "",
  proof: "",
  sort: "ledger",
  page: 0,
  sourceDocumentId: "",
  sourceFilename: "",
}
export function paymentTableDraftName(
  params: LedgerQueryParams = {},
  investigation = false
) {
  return `payment-table:${JSON.stringify([
    investigation,
    params.accountId ?? null,
    params.startDate ?? null,
    params.endDate ?? null,
    params.ledgerStatus ?? "admitted",
  ])}`
}
export function resetPaymentTableView(
  caseId: string,
  params: LedgerQueryParams,
  statement?: { source_document_id?: string; filename?: string }
) {
  useFinancialDraftStore
    .getState()
    .put(financialDraftKey(caseId, paymentTableDraftName(params, true)), {
      ...emptyPaymentTableView,
      sourceDocumentId: statement?.source_document_id || "",
      sourceFilename: statement?.filename || "",
    })
}
