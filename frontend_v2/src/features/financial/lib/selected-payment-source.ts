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
  return checkedSelectedPayment(data, caseId, id)
}

function checkedSelectedPayment(
  data: ReturnType<typeof citationSchema.parse>,
  caseId: string,
  id: string
) {
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

/** The transport batch is independent of the number of payments selected. */
export async function readSelectedPayments(
  caseId: string,
  ids: string[],
  signal?: AbortSignal
) {
  if (!ids.length) return []
  const raw = await fetchAPI<{ case_id: string; sources: unknown[] }>(
    `/api/financial/ledger/sources?${new URLSearchParams({ case_id: caseId })}`,
    { method: "POST", body: { transaction_ids: ids }, signal }
  )
  if (
    raw.case_id !== caseId ||
    !Array.isArray(raw.sources) ||
    raw.sources.length !== ids.length
  )
    throw Error(
      "Some selected payment details are missing. No selection was saved."
    )
  return raw.sources.map((source, index) =>
    checkedSelectedPayment(citationSchema.parse(source), caseId, ids[index])
  )
}
