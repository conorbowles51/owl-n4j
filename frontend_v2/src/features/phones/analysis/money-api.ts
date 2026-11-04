import { fetchAPI } from "@/lib/api-client"
import type { AmountReading } from "./money-words"

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

/** A person's decision on a result. "not_pursued" is a decision not to act (07 section 14): the lead may be right and
 * is not being followed, for the reason given; it says nothing about whether the result is correct. */
export type AnalysisDecisionKind = "confirmed" | "rejected" | "not_pursued"
export interface AnalysisDecision { decision: AnalysisDecisionKind; reason: string; by: string; at: string }

/**
 * What a money reading or an account lead measured (the server's `measures`). Every field is optional: the two kinds
 * carry different ones, and the server may add more.
 */
/** 05 section 4.3.8: a ledger row that could be the reading, with its strength by rule and a person's decision. */
export type PairLevel = "strong" | "moderate" | "weak" | "faint"
export type PairDecision = "confirmed" | "rejected"
export interface Pairing {
  transaction_id: string
  ref_id: string | null
  amount_minor: number | null
  currency: string | null
  date: string | null
  lag_days?: number
  level: PairLevel
  fits?: { amount: number; date: number; account: number }
  reasons: { match: string[]; substantiation: string[] }
  rule_match?: boolean
  found_by_rule: boolean
  rule_words: string
  decision: PairDecision | null
  decision_words: string | null
  decision_note?: string
}
export interface PairCounts { by_level: Record<PairLevel, number>; confirmed: number; rejected: number }

export interface MoneyMeasures extends AmountReading {
  direction?: string | null
  source?: string | null
  phone_label?: string | null
  event_instant?: string | null
  device_zone?: string | null
  institution?: { name: string } | null
  account_ref?: string | null
  outcome?: string | null
  reason?: string | null
  sentence?: string | null
  status?: string | null
  record_uid?: string
  field_path?: string
  pairings?: Pairing[]
  pair_counts?: PairCounts
  pairings_left_out_words?: string | null
  best_level?: PairLevel | null
  [key: string]: unknown
}

export interface AnalysisResult {
  id: string
  kind: "money_reading" | "account_lead"
  strength: string
  label: string
  measures: MoneyMeasures
  directions: { supports: Direction[]; undercuts: Direction[] }
  decision: AnalysisDecisionKind | null
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
  results: (caseId: string, runId: string, kind: string, strength: string, offset: number, limit = 100, order = "strength") =>
    fetchAPI<ResultPage>(`${BASE}/runs/${runId}/results?${q({ case_id: caseId, kind, strength, offset, limit, order })}`),
  decidePair: (caseId: string, recordUid: string, fieldPath: string, transactionId: string, decision: PairDecision | "undo", note: string) =>
    fetchAPI<{ decision: PairDecision | null; decision_words: string | null }>(`${BASE}/money/pairs/decisions`, {
      method: "POST",
      body: { case_id: caseId, record_uid: recordUid, field_path: fieldPath, transaction_id: transactionId, decision, note: note || null },
    }),
  orphaned: (caseId: string) =>
    fetchAPI<{ items: { record_uid: string; transaction_id: string; field_path: string; decision: PairDecision; decision_words: string; pair: { ref_id?: string; amount_minor?: number; currency?: string; date?: string } }[]; search: string }>(
      `${BASE}/money/pairs/orphaned?${q({ case_id: caseId })}`),
  detail: (caseId: string, resultId: string) =>
    fetchAPI<AnalysisResult & { records: ResultRecord[] }>(`${BASE}/results/${resultId}?${q({ case_id: caseId })}`),
  decide: (caseId: string, resultId: string, decision: AnalysisDecisionKind, reason: string) =>
    fetchAPI<AnalysisResult>(`${BASE}/results/${resultId}/decisions`, { method: "POST", body: { case_id: caseId, decision, reason } }),
  ledgerLinks: (caseId: string, transactionIds: string[]) =>
    fetchAPI<{ links: Record<string, PhoneLink[]> }>(`${BASE}/money/ledger-links`, { method: "POST", body: { case_id: caseId, transaction_ids: transactionIds }, read: true }),
}
