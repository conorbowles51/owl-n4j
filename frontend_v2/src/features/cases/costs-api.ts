import { fetchAPI } from "@/lib/api-client"

/** One line of a case's AI cost report: a document, a batch, a conversation or a kind of work (FEAT-007). */
export interface CaseCostLine {
  kind: string
  label: string
  evidence_file_id: string | null
  calls: number
  tokens: number
  models: string[]
  cost_usd: number
  cost_exact: string
  first_at: string | null
  last_at: string | null
}

export interface CaseCostReport {
  case_id: string
  case_title: string
  start_date: string | null
  end_date: string | null
  lines: CaseCostLine[]
  line_count: number
  call_count: number
  total_tokens: number
  total_cost_usd: number
  total_cost_exact: string
  generated_at: string
}

const query = (caseId: string, start?: string, end?: string) =>
  new URLSearchParams({ case_id: caseId, ...(start ? { start_date: start } : {}), ...(end ? { end_date: end } : {}) })

export const caseCostsAPI = {
  report: (caseId: string, start?: string, end?: string) =>
    fetchAPI<CaseCostReport>(`/api/cost-ledger/case-report?${query(caseId, start, end)}`),

  /** The same report as a PDF file; the server's refusal (e.g. too many lines) comes back as the error message. */
  downloadPdf: async (caseId: string, start?: string, end?: string) => {
    const response = await fetch(`/api/cost-ledger/case-report.pdf?${query(caseId, start, end)}`, {
      credentials: "include",
    })
    if (!response.ok) {
      let message = `The PDF could not be made (${response.status}).`
      try {
        const data = (await response.json()) as { detail?: unknown }
        if (typeof data.detail === "string") message = data.detail
      } catch {
        // Keep the status message.
      }
      throw new Error(message)
    }
    const blob = await response.blob()
    const quoted = (response.headers.get("Content-Disposition") ?? "").match(/filename="([^"]+)"/)?.[1]
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = quoted || "ai-costs.pdf"
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}
