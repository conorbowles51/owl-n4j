import { fetchAPI } from "@/lib/api-client"

/** The system's readings of a case's phones and the decisions on them (02 sections 6.8, 6.10; 07 J-8). */
export type ReadingStatus = "open" | "confirmed" | "corrected"

export interface ReadingChoice {
  id: string
  label: string
}

export interface Reading {
  id: string
  extraction_id: string
  phone: string
  type_name: string
  type_words: string
  rule_id: string
  part: string
  sentence: string
  records: number
  status: ReadingStatus
  origin: string | null
  resolved_by: string | null
  resolved_at: string | null
  reason: string | null
  reason_kind: "typed" | "standard" | null
  note: string | null
  choices: ReadingChoice[]
}

export interface ReadingQueue {
  case_id: string
  total: number
  open: number
  checked: number
  items: Reading[]
}

export interface ExampleParty {
  role: string | null
  name: string | null
  identifier: string | null
  is_owner: boolean
  implicit_owner: boolean
  mapped_by_this: boolean
}

export interface ExampleTime {
  field: string
  instant: string | null
  original_text: string | null
  is_event_time: boolean
  mapped_by_this: boolean
}

export interface ExampleRecord {
  record_uid: string
  type_words: string | null
  kind: string | null
  direction: string | null
  app: string | null
  instant: string | null
  text: string | null
  subject: string | null
  title: string | null
  deleted_state: string | null
  parties: ExampleParty[]
  times: ExampleTime[]
}

export interface ExampleKind {
  id: string
  label: string
  record_uid: string
  count: number
  number: number
  example: ExampleRecord
}

export interface ReadingExamples {
  id: string
  records: number
  kinds: ExampleKind[]
  apps_not_shown: number
}

export interface PhoneProgress {
  extraction_id: string
  phone: string | null
  state: "waiting" | "re-reading" | "done"
  records_total: number
  records_done: number
  seconds_left: number | null
}

export interface ConfirmResult {
  decision_id: string
  status: ReadingStatus
  reason: string
  reason_kind: "standard"
  resolved_by: string
}

export interface CorrectResult {
  decision_id: string
  status: ReadingStatus
  scope: string[]
  extraction_ids: string[]
  choice: string
}

export interface ConfirmKindResult {
  confirmed: { id: string; sentence: string; decision_id: string; reason: string }[]
  refused: { id: string; sentence: string | null; reason: string }[]
  not_listed: number
  resolved_by: string
  words: string
}

export interface CorrectionPreview {
  records: number
  without: string | null
  phones: { extraction_id: string; phone: string; records: number }[]
  words: string | null
}

export interface RecheckItem {
  task_id: string
  confirmation_id: string
  phone: string | null
  extraction_id: string
  sentence: string | null
  first: { by_id?: string; by_name?: string; at?: string; reason?: string }
  result: { agrees: boolean; note: string | null; by_name: string; at: string } | null
  earlier_results: number
  reading_id: string | null
  status_now: ReadingStatus | null
  mine: boolean
  own_confirmation: boolean
}

export interface RecheckSummary {
  sampled: number
  agrees: number
  disagrees: number
  pending: number
  rate_percent: number | null
  too_few: boolean
  words: string
  min_base: number
  percent: number
  passes: { pass_id: string; task_id: string; title: string; seed: number; percent: number; eligible: number; reviewer: string | null; sampled: number }[]
  items: RecheckItem[]
}

const q = (caseId: string) => `case_id=${encodeURIComponent(caseId)}`

export const readingsAPI = {
  list: (caseId: string) => fetchAPI<ReadingQueue>(`/api/phones/readings?${q(caseId)}`),
  examples: (caseId: string, id: string) => fetchAPI<ReadingExamples>(`/api/phones/readings/${id}/examples?${q(caseId)}`),
  progress: (caseId: string) => fetchAPI<{ phones: PhoneProgress[] }>(`/api/phones/readings/progress?${q(caseId)}`),
  confirm: (caseId: string, id: string, body: { viewed: string[]; opened: string[]; note?: string; expected_status: ReadingStatus }) =>
    fetchAPI<ConfirmResult>(`/api/phones/readings/${id}/confirm`, { method: "POST", body: { case_id: caseId, ...body } }),
  correct: (
    caseId: string,
    id: string,
    body: { choice: string; reason: string; scope: "this_phone" | "same_format"; note?: string; expected_status: ReadingStatus; expected_empty: number }
  ) => fetchAPI<CorrectResult>(`/api/phones/readings/${id}/correct`, { method: "POST", body: { case_id: caseId, ...body } }),
  /** What a correction would leave empty, with nothing written (07 J-8 failure state). */
  correctionPreview: (caseId: string, id: string, body: { choice: string; scope: "this_phone" | "same_format" }) =>
    fetchAPI<CorrectionPreview>(`/api/phones/readings/${id}/correct/preview`, { method: "POST", body: { case_id: caseId, ...body } }),
  /** Looks right for the listed rows of one kind on one phone, each its own decision (07 J-8 step 6). */
  confirmKind: (caseId: string, rows: { id: string; viewed: string[]; opened: string[] }[], note?: string) =>
    fetchAPI<ConfirmKindResult>("/api/phones/readings/confirm-kind", { method: "POST", body: { case_id: caseId, rows, note } }),
  rechecks: (caseId: string) => fetchAPI<RecheckSummary>(`/api/phones/readings/rechecks?${q(caseId)}`),
  drawRecheck: (caseId: string, reviewer: string) =>
    fetchAPI<{ words: string; task_id: string; sample: number; eligible: number }>("/api/phones/readings/rechecks", { method: "POST", body: { case_id: caseId, reviewer } }),
  recordRecheck: (caseId: string, taskId: string, confirmationId: string, agrees: boolean, note: string) =>
    fetchAPI<{ left: number }>("/api/phones/readings/rechecks/result", {
      method: "POST",
      body: { case_id: caseId, task_id: taskId, confirmation_id: confirmationId, agrees, note: note.trim() || null },
    }),
}
