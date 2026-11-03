import { fetchAPI } from "@/lib/api-client"
import type { Judgement } from "./judgements"

/** A deterministic proceeds calculation (backend services/financial/proceeds.py); every assumption is a judgement
 * call a named person sets with its source. The result is an estimate, not a measurement. */
export interface ProceedsAssumption {
  key: "messages" | "share_deals" | "deals_per_message" | "price_per_deal"
  label: string
  unit: string
  kind: "count" | "percent" | "ratio" | "money"
  current: Judgement | null
  set_by: string | null
  low: string | null
  high: string | null
  source: string | null
  proposed: Judgement[]
  history: Judgement[]
}

export interface ProceedsMove {
  key: string
  label: string
  at_low_minor: number
  at_high_minor: number
  swing_minor: number
}

export interface ProceedsView {
  id: string
  case_id: string
  title: string
  currency: string
  period_start: string | null
  period_end: string | null
  created_by: string
  label: string
  formula: string
  assumptions: ProceedsAssumption[]
  result: { low_minor: number; mid_minor: number; high_minor: number; moves: ProceedsMove[] } | null
  missing: string[]
  deposits: {
    categories: string[]
    verified_minor: number
    verified_rows: number
    left_out_rows: number
    left_out_classes: Record<string, number>
    other_currency_rows?: number
    note: string
  }
}

const base = "/api/financial/judgements/proceeds"
const q = (caseId: string) => `case_id=${encodeURIComponent(caseId)}`

export const proceedsKeys = {
  all: (caseId: string) => ["financial-judgements", caseId, "proceeds"] as const,
  one: (caseId: string, id: string) => ["financial-judgements", caseId, "proceeds", id] as const,
}

export function listProceeds(caseId: string) {
  return fetchAPI<{ items: { id: string; title: string; currency: string; created_by: string }[]; total: number }>(
    `${base}/list?${q(caseId)}`
  )
}

export function getProceeds(caseId: string, id: string) {
  return fetchAPI<ProceedsView>(`${base}/${id}?${q(caseId)}`)
}

export function createProceeds(
  caseId: string,
  body: { title: string; currency: string; period_start?: string | null; period_end?: string | null; deposit_categories?: string[] }
) {
  return fetchAPI<ProceedsView>(`${base}?${q(caseId)}`, { method: "POST", body })
}

export function setAssumption(caseId: string, id: string, key: string, body: { low: string; high: string; source: string; reason?: string }) {
  return fetchAPI<ProceedsView>(`${base}/${id}/assumptions/${key}?${q(caseId)}`, { method: "POST", body })
}

export function confirmAssumption(caseId: string, id: string, key: string, judgementId: string) {
  return fetchAPI<ProceedsView>(`${base}/${id}/assumptions/${key}/${judgementId}/confirm?${q(caseId)}`, { method: "POST" })
}

/** Minor units in the calculation's currency, using the currency's own number of decimals. */
export function proceedsMoney(minor: number, currency: string) {
  try {
    const format = new Intl.NumberFormat("en-US", { style: "currency", currency })
    const digits = format.resolvedOptions().maximumFractionDigits ?? 2
    return format.format(minor / 10 ** digits)
  } catch {
    return `${minor} (minor units) ${currency}`
  }
}
