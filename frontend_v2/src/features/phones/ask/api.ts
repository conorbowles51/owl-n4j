import { fetchAPI } from "@/lib/api-client"

/** Ask the phones a question (lx-phoneask; backend routers/phone_ask.py). */
export interface AskPhone { extraction_id: string; label: string; owner: string | null; allowed: boolean | null }
export interface CiteLabel { record: string; label: string; extraction_id: string | null }
export interface ElsewhereRow { source: string; text: string; cite?: string; cite_label?: string; relation: string; reason?: string }
export interface Statement {
  text: string
  cites: string[]
  cite_labels: CiteLabel[]
  people: string[]
  date_from: string | null
  date_to: string | null
  elsewhere: { rows: ElsewhereRow[] | null; note: string | null; searched?: string[] }
}
export interface StepAction { label: string; kind: string; extraction_id?: string; date?: string | null; statement?: number; record?: string; q?: string }
export interface Step { n: number; kind: string; title: string; why: string; action: StepAction; statement?: number }
export interface Answer {
  question: string
  phones: AskPhone[]
  read: string[]
  left_out: string[]
  searched: string
  statements: Statement[]
  not_found: { asked: string; text: string }[]
  notes: string[]
  steps: Step[]
  label: string
  records_used: (CiteLabel & { cited: boolean })[]
  model: string | null
  error: string | null
}
export interface AskRow {
  id: string
  question: string
  phones: string[]
  status: "running" | "done" | "failed"
  error: string | null
  answer: Answer | null
  asked_by_name: string
  created_at: string | null
  seconds: number | null
}
export interface Earlier { total: number; shown: number; offset: number; next_offset: number | null; items: { id: string; question: string; status: string; asked_by_name: string; created_at: string | null; statements: number | null }[] }

const base = (caseId: string) => `/api/cases/${encodeURIComponent(caseId)}/phones/ask`

export const askAPI = {
  ask: (caseId: string, question: string, phones: string[]) =>
    fetchAPI<AskRow>(base(caseId), { method: "POST", body: { question, phones: phones.length ? phones : null } }),
  read: (caseId: string, id: string) => fetchAPI<AskRow>(`${base(caseId)}/${encodeURIComponent(id)}`),
  earlier: (caseId: string, offset = 0, limit = 20) => fetchAPI<Earlier>(`${base(caseId)}?offset=${offset}&limit=${limit}`),
}
