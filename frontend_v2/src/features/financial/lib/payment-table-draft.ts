import type { LedgerQueryParams } from "../hooks/use-ledger-transactions"
import { useInvestigationScopeStore } from "../stores/investigation-scope"
import {
  financialDraftKey,
  useFinancialDraftStore,
} from "../stores/financial-drafts"

export const emptyPaymentTableView = {
  accountId: "",
  accountHolder: "",
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
  importBatchId: "",
  importBatchRevision: "",
  importSourceIds: [] as string[],
  importStatementCount: 0,
}

export function showAllImportedPayments(caseId: string) {
  resetPaymentTableView(caseId, {})
  useFinancialDraftStore
    .getState()
    .put(financialDraftKey(caseId, "investigation-category"), "")
  useInvestigationScopeStore.getState().apply(caseId, {})
}

export function retainPaymentTableView(
  caseId: string,
  previous: LedgerQueryParams,
  next: LedgerQueryParams
) {
  const store = useFinancialDraftStore.getState()
  const current = store.drafts[
    financialDraftKey(caseId, paymentTableDraftName(previous, true))
  ] as typeof emptyPaymentTableView | undefined
  store.put(financialDraftKey(caseId, paymentTableDraftName(next, true)), {
    ...emptyPaymentTableView,
    ...current,
    page: 0,
  })
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
  statement?: {
    source_document_id?: string
    filename?: string
    batch_id?: string
    revision?: string
    source_document_ids?: string[]
    statement_count?: number
  }
) {
  // An explicit result link must show its payments even if the previous screen
  // was narrowed to a category that none of these new payments has yet.
  useFinancialDraftStore
    .getState()
    .put(financialDraftKey(caseId, "investigation-category"), "")
  useFinancialDraftStore
    .getState()
    .put(financialDraftKey(caseId, paymentTableDraftName(params, true)), {
      ...emptyPaymentTableView,
      sourceDocumentId: statement?.source_document_id || "",
      sourceFilename: statement?.filename || "",
      importBatchId: statement?.batch_id || "",
      importBatchRevision: statement?.revision || "",
      importSourceIds: statement?.source_document_ids || [],
      importStatementCount: statement?.statement_count || 0,
    })
}
