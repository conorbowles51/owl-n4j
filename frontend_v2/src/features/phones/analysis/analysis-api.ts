import { fetchAPI } from "@/lib/api-client"
import type { Snapshot } from "@/features/pattern/api"
import type { AnalysisDecision, AnalysisRun, Direction, ResultRecord } from "./money-api"

/** The phone analysis API (05 section 3.4) for any approach. Approach 1 keeps its own wrapper in money-api. */

export interface ApproachResult {
  id: string
  kind: string
  strength: string
  label: string
  measures: Record<string, unknown>
  directions: { supports: Direction[]; undercuts: Direction[] }
  decision: "confirmed" | "rejected" | null
  decisions: AnalysisDecision[]
  period_start: string | null
  period_end: string | null
}

/** A kept approach result: the pattern snapshot shape with its own kind (02 decision 50). */
export type KeptResult = Omit<Snapshot, "kind"> & { kind: "analysis_result" }

export interface ApproachPage { total: number; offset: number; limit: number; items: ApproachResult[] }

const BASE = "/api/phone-analysis"
const q = (o: Record<string, string | number | undefined>) =>
  Object.entries(o).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&")

export function analysisAPI(approach: string) {
  return {
    approach,
    runs: (caseId: string) => fetchAPI<{ items: AnalysisRun[] }>(`${BASE}/runs?${q({ case_id: caseId, approach })}`),
    request: (caseId: string, parameters?: Record<string, unknown>) =>
      fetchAPI<AnalysisRun>(`${BASE}/runs`, { method: "POST", body: { case_id: caseId, approach, ...(parameters ? { parameters } : {}) } }),
    run: (caseId: string, runId: string) => fetchAPI<AnalysisRun>(`${BASE}/runs/${runId}?${q({ case_id: caseId })}`),
    cancel: (caseId: string, runId: string) => fetchAPI<AnalysisRun>(`${BASE}/runs/${runId}/cancel?${q({ case_id: caseId })}`, { method: "POST" }),
    coverage: (caseId: string) => fetchAPI<{ sentence: string }>(`${BASE}/coverage?${q({ case_id: caseId, approach })}`),
    results: (caseId: string, runId: string, f: { kind?: string; strength?: string; offset: number; limit?: number }) =>
      fetchAPI<ApproachPage>(`${BASE}/runs/${runId}/results?${q({ case_id: caseId, kind: f.kind, strength: f.strength, offset: f.offset, limit: f.limit ?? 100 })}`),
    detail: (caseId: string, resultId: string) =>
      fetchAPI<ApproachResult & { records: ResultRecord[] }>(`${BASE}/results/${resultId}?${q({ case_id: caseId })}`),
    keep: (caseId: string, resultId: string) =>
      fetchAPI<KeptResult>(`${BASE}/results/${resultId}/keep`, { method: "POST", body: { case_id: caseId } }),
    decide: (caseId: string, resultId: string, decision: "confirmed" | "rejected", reason: string) =>
      fetchAPI<ApproachResult>(`${BASE}/results/${resultId}/decisions`, { method: "POST", body: { case_id: caseId, decision, reason } }),
  }
}

export type AnalysisClient = ReturnType<typeof analysisAPI>
