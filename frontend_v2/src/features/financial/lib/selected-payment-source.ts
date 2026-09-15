import { fetchAPI } from "@/lib/api-client"
import { citationSchema } from "./source-citation"

export async function readSelectedPayment(
  caseId: string,
  id: string,
  signal?: AbortSignal
) {
  const data = citationSchema.parse(
    await fetchAPI(
      `/api/financial/ledger/${encodeURIComponent(id)}/source?${new URLSearchParams({ case_id: caseId })}`,
      { signal }
    )
  )
  if (
    data.case_id !== caseId ||
    data.transaction_id !== id ||
    !data.transaction ||
    data.transaction.key !== id ||
    data.transaction.case_id !== caseId ||
    data.transaction.source_document_id !== data.source_document_id ||
    data.transaction.ledger_status !== data.ledger_status ||
    data.transaction.superseded_by_id !== data.superseded_by_id
  )
    throw Error(
      "The payment details did not match this selection. Reload its details before continuing."
    )
  return { ...data, transaction: data.transaction }
}
