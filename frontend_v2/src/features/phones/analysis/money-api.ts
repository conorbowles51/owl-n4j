import { fetchAPI } from "@/lib/api-client"

/** The phone analysis API (05 section 3.4) as approach 1, money signals, uses it. */

export interface AnalysisRun {
  id: string
  approach: string
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | "superseded"
  progress: { read?: number; total?: number } | null
  coverage: { sentence?: string } | null
  counts: Record<string, unknown> | null
  error: string | null
  created_at: string | null
  finished_at: string | null
}

export interface Direction { code: string; detail: string; locators: string[] }

export interface AnalysisDecision { decision: "confirmed" | "rejected"; reason: string; by: string; at: string }

export interface AnalysisResult {
  id: string
  kind: "money_reading" | "account_lead"
  strength: string
  label: string
  measures: Record<string, any>
  directions: { supports: Direction[]; undercuts: Direction[] }
  decision: "confirmed" | "rejected" | null
  decisions: AnalysisDecision[]
  period_start: string | null
}

export interface ResultPage { total: number; offset: number; limit: number; items: AnalysisResult[] }

export interface ResultRecord {
  record_uid: string | null
  extraction_id: string | null
  field_path: string | null
  ledger_transaction_id: string | null
  ledger_ref_id: string | null
  role: string
}

export interface PhoneLink {
  phone_label: string | null
  source: string | null
  instant: string | null
  record_uid: string
  url: string
  result_id: string
  outcome: string | null
}

const BASE = "/api/phone-analysis"
const q = (o: Record<string, string | number | undefined>) =>
  Object.entries(o).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&")

export const moneyAPI = {
  runs: (caseId: string) => fetchAPI<{ items: AnalysisRun[] }>(`${BASE}/runs?${q({ case_id: caseId, approach: "money_signals" })}`),
  request: (caseId: string) =>
    fetchAPI<AnalysisRun>(`${BASE}/runs`, { method: "POST", body: { case_id: caseId, approach: "money_signals" } }),
  run: (caseId: string, runId: string) => fetchAPI<AnalysisRun>(`${BASE}/runs/${runId}?${q({ case_id: caseId })}`),
  cancel: (caseId: string, runId: string) => fetchAPI<AnalysisRun>(`${BASE}/runs/${runId}/cancel?${q({ case_id: caseId })}`, { method: "POST" }),
  coverage: (caseId: string) => fetchAPI<{ sentence: string }>(`${BASE}/coverage?${q({ case_id: caseId, approach: "money_signals" })}`),
  results: (caseId: string, runId: string, kind: string, strength: string, offset: number, limit = 100) =>
    fetchAPI<ResultPage>(`${BASE}/runs/${runId}/results?${q({ case_id: caseId, kind, strength, offset, limit })}`),
  detail: (caseId: string, resultId: string) =>
    fetchAPI<AnalysisResult & { records: ResultRecord[] }>(`${BASE}/results/${resultId}?${q({ case_id: caseId })}`),
  decide: (caseId: string, resultId: string, decision: "confirmed" | "rejected", reason: string) =>
    fetchAPI<AnalysisResult>(`${BASE}/results/${resultId}/decisions`, { method: "POST", body: { case_id: caseId, decision, reason } }),
  ledgerLinks: (caseId: string, transactionIds: string[]) =>
    fetchAPI<{ links: Record<string, PhoneLink[]> }>(`${BASE}/money/ledger-links`, { method: "POST", body: { case_id: caseId, transaction_ids: transactionIds }, read: true }),
}
