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
    body: { choice: string; reason: string; scope: "this_phone" | "same_format"; note?: string; expected_status: ReadingStatus }
  ) => fetchAPI<CorrectResult>(`/api/phones/readings/${id}/correct`, { method: "POST", body: { case_id: caseId, ...body } }),
}
