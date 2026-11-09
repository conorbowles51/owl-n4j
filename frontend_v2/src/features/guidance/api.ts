import { fetchAPI } from "@/lib/api-client"

/**
 * Guidance settings and step history, kept per person on the server (backend routers/guidance.py and
 * routers/step_history.py), so a choice follows the person to any browser and survives sign-out.
 */
export interface GuidanceSettings {
  guidance: "on" | "off"
  /** Whose choice it is: the person's own, the case default an admin set, or the app default (on). */
  source: "user" | "case" | "default"
  case_default: "on" | "off" | null
  tips_off: string[]
  tours: Record<string, { state?: "done" | "skipped"; step?: number }>
  history_collapsed: boolean
}

export interface StartCounts {
  files: number | null
  unprocessed: number | null
  phones: number | null
  payments: number | null
  theories: number | null
  unavailable: string[]
}

export interface StepItem {
  kind: string
  id: string
  label?: string
}

export interface Step {
  id: string
  at: string
  name: string
  screen: string
  path: string
  state: Record<string, unknown>
  item: StepItem | null
  merged?: boolean
}

export interface StepList {
  steps: Step[]
  total: number
  keep_days: number
}

const q = (caseId: string | null | undefined) => (caseId ? `?case_id=${encodeURIComponent(caseId)}` : "")

export const guidanceKey = (caseId: string | null | undefined) => ["guidance", caseId ?? null] as const
export const stepsKey = (caseId: string) => ["step-history", caseId] as const

export const guidanceAPI = {
  me: (caseId?: string | null) => fetchAPI<GuidanceSettings>(`/api/guidance/me${q(caseId)}`),
  set: (guidance: "on" | "off", caseId?: string | null) =>
    fetchAPI<GuidanceSettings>("/api/guidance/me", { method: "PUT", body: { guidance, case_id: caseId ?? null } }),
  hideTip: (kind: string, caseId?: string | null) =>
    fetchAPI<GuidanceSettings>("/api/guidance/me/tips-off", { method: "POST", body: { kind, case_id: caseId ?? null } }),
  showAgain: (caseId?: string | null) =>
    fetchAPI<GuidanceSettings>(`/api/guidance/me/show-again${q(caseId)}`, { method: "POST" }),
  tour: (area: string, body: { state?: "done" | "skipped" | "reset"; step?: number }, caseId?: string | null) =>
    fetchAPI<GuidanceSettings>(`/api/guidance/me/tours/${encodeURIComponent(area)}`, {
      method: "PUT",
      body: { ...body, case_id: caseId ?? null },
    }),
  history: (collapsed: boolean, caseId?: string | null) =>
    fetchAPI<GuidanceSettings>("/api/guidance/me/history", { method: "PUT", body: { collapsed, case_id: caseId ?? null } }),
  caseDefault: (caseId: string, guidance: "on" | "off" | null) =>
    fetchAPI<GuidanceSettings>(`/api/guidance/cases/${encodeURIComponent(caseId)}/default`, { method: "PUT", body: { guidance } }),
  start: (caseId: string) => fetchAPI<StartCounts>(`/api/guidance/cases/${encodeURIComponent(caseId)}/start`),
}

const h = (caseId: string) => `/api/history/cases/${encodeURIComponent(caseId)}`

export const historyAPI = {
  list: (caseId: string, opts: { limit?: number; offset?: number; q?: string } = {}) => {
    const p = new URLSearchParams({ limit: String(opts.limit ?? 8) })
    if (opts.offset) p.set("offset", String(opts.offset))
    if (opts.q?.trim()) p.set("q", opts.q.trim())
    return fetchAPI<StepList>(`${h(caseId)}?${p}`)
  },
  record: (caseId: string, body: Omit<Step, "id" | "at" | "merged" | "item"> & { item?: StepItem | null; replaces?: string | null }) =>
    fetchAPI<Step>(h(caseId), { method: "POST", body }),
  get: (caseId: string, stepId: string) => fetchAPI<Step>(`${h(caseId)}/steps/${encodeURIComponent(stepId)}`),
  clear: (caseId: string) => fetchAPI<{ removed: number }>(h(caseId), { method: "DELETE" }),
}
