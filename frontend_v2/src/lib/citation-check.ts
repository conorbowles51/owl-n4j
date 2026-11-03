import { fetchAPI } from "@/lib/api-client"

/** What the case says about one citation (POST /api/citations/resolve; backend services/case_citations.py). */
export interface CitationResolution {
  href: string
  scheme: "doc" | "txn" | "rec"
  status: "ok" | "not_in_case" | "ambiguous"
  reason?: string
  page?: number
  page_given: boolean
  evidence_file_id?: string
  filename?: string
  candidates?: { evidence_file_id: string; filename: string; uploaded_at?: string | null; size?: number }[]
  transaction_id?: string
  record_uid?: string
  field?: string
  legacy: boolean
  detail?: { ledger_status?: string; superseded_by_id?: string }
}

/** Check citations against the case in one request; the answer is keyed by href. */
export async function resolveCitations(caseId: string, hrefs: string[], signal?: AbortSignal) {
  const answer = await fetchAPI<{ items: CitationResolution[] }>("/api/citations/resolve", {
    method: "POST",
    body: { case_id: caseId, hrefs },
    signal,
  })
  return new Map(answer.items.map((item) => [item.href, item]))
}
