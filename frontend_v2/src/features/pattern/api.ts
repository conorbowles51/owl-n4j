import { fetchAPI } from "@/lib/api-client"

/** Pattern of life and the statement check (docs/cellebrite/04 section 10). Times are ISO 8601 with offset. */
export type Subject = { kind: "extraction"; extraction_id: string } | { kind: "dossier"; dossier_id: string }

export interface SubjectPhone {
  kind: "extraction"
  extraction_id: string
  label: string
  device_zone: string | null
  first: string | null
  last: string | null
  projection_status: string
  event_count: number
  /** The days the phone's activity covers, with stray far-off dates set apart and counted (04 decision 38). */
  usual_span: UsualSpan | null
}

export interface UsualSpan {
  first: string | null
  last: string | null
  set_apart: number
  set_apart_first: string | null
  set_apart_last: string | null
}

/** Every event of one counted group of a check (04 decision 37), paged. */
export interface GroupEvents {
  ordinal: number
  stored_count: number
  total: number
  cursor: number
  limit: number
  returned: number
  next_cursor: number | null
  changed_since_check: boolean
  items: { activity_event_id: number; at_utc: string; end_utc: string | null; record_uid: string | null; field_path: string | null
    display: { type: string; field: string; meaning: string | null; source_app: string | null; activity_class: string; actor: string } }[]
}

export interface SubjectPerson {
  kind: "dossier"
  dossier_id: string
  name: string
  extraction_ids: string[]
}

export interface SubjectList {
  extractions: SubjectPhone[]
  dossiers: SubjectPerson[]
  total_extractions: number
  total_dossiers: number
}

export interface HourState {
  hour_utc: string
  state: string
  words: string
  /** The hour holds at least one record of the phone (a no_data hour then never reads "No data"). */
  has_records?: boolean
}

export interface LaneItem {
  ref_kind: string
  id: string | number
  at: string
  end: string | null
  field?: string
  meaning?: string
  class?: string
  strength?: string
  actor?: string
  flags?: string[]
  source_app?: string | null
  kind?: string
  direction?: string
  parties?: { name: string | null; identifier: string | null; role: string | null }[]
  extraction_id?: string
  phone?: string | null
  record_uid?: string | null
  record_type?: string | null
  radius_m?: number | null
  source_kind?: string
  /** The record's stream family (04 5.2): notifications, web, app_usage, sensors, wifi, ... */
  family?: string | null
}

export interface MoneyItem {
  transaction_id: string
  day: string
  date_basis: string
  date_words: string
  amount_minor: number
  currency: string
  direction: string
  counterparty: string | null
  description: string | null
  time_of_day: null
  place: { lat: number; lon: number; radius_m: number; actor_name: string } | null
}

export interface DayWindow {
  lanes: Record<string, LaneItem[]>
  availability: { extraction_id: string; phone: string | null; hours: HourState[] }[]
  totals: Record<string, number>
  lane_words: Record<string, string>
  flag_words?: Record<string, string>
  truncated: boolean
  passive_as_hourly_counts: boolean
  passive_hours: { hour_utc: string; count: number }[] | null
  limit_words: string | null
}

export interface DayResponse extends DayWindow {
  date: string
  zone: string
  start: string
  end: string
}

export interface WindowResponse {
  start: string
  end: string
  span: string
  zone: string
  zone_basis?: string
  zone_note?: string | null
  phones: (DayWindow & { extraction_id: string; label: string | null })[]
  phones_total: number
  money: MoneyItem[]
  money_total: number
  /** The whole day (YYYY-MM-DD) when the anchor has a date and no time (a payment); null otherwise. */
  date_only?: string | null
}

export interface GridResponse {
  days: { date: string; hours: { state: string; counts: Record<string, number>; phones?: string[] }[] }[]
  quiet_hours: { start_hour: number; end_hour: number; hours: number[]; words?: string } | null
  quiet_words?: string
  breaks: { date: string; items?: unknown[]; state?: string }[]
  not_observed?: { date: string }[]
  zone: string
  [k: string]: unknown
}

export interface TogetherItemRow {
  ordinal: number
  verdict: string
  basis: string
  at_utc: string
  distance_m: number | null
  a_lat: number | null
  a_lon: number | null
  b_lat: number | null
  b_lon: number | null
}

export interface TogetherResponse {
  items?: TogetherItemRow[]
  next_cursor?: number | null
  label?: string
  id?: string
  run_id?: string
  status: string
  estimated_pairs?: number
  total?: number
  returned?: number
  counts?: Record<string, number>
  episodes?: { kind: string; start: string; end: string; items: number; breadth: string | null }[]
  params?: Record<string, unknown>
  [k: string]: unknown
}

export type ClaimKind =
  | "inactive" | "active" | "at_place" | "not_at_place" | "with_subject" | "apart_from_subject" | "no_contact" | "contact"

export interface Claim {
  id: string
  version: number
  status: "draft" | "confirmed" | "withdrawn"
  status_words: string
  kind: ClaimKind
  subject: Subject
  window_start: string | null
  window_end: string | null
  window_zone: string | null
  window_text: string | null
  place: { lat?: number; lon?: number; radius_m?: number; text?: string } | null
  counterpart: Record<string, unknown> | null
  origin: "manual" | "ai_draft"
  ai_model: string | null
  missing_for_confirm: string[]
}

export interface EvaluationItem {
  ordinal: number
  role: "contradicting" | "supporting" | "context" | "gap"
  ref_kind: string
  ref_id: string
  strength: string | null
  reason_code: string
  explanation: string
  record_uid: string | null
  extraction_id: string | null
  at_utc: string | null
  end_utc: string | null
  display: Record<string, unknown>
  disputed: { reason: string; actor_name: string } | null
}

export interface Evaluation {
  evaluation_id: string
  claim_id: string
  claim_version: number
  evaluated_at?: string
  outcome: string
  outcome_basis: string
  outcome_words: string
  stale: boolean
  window: { start: string; end: string; zone: string }
  summary: { not_yet_checked?: { code: string; count: number | null; words: string }[] }
  counts: { contradicting: Record<string, number>; supporting: Record<string, number>; gap: number; context: number }
  total_items: number
  items: EvaluationItem[]
  disputed_items: number
}

export interface PlaceObservation {
  id: number
  extraction_id: string | null
  record_uid: string | null
  kind: string
  source_kind: string
  lat: number
  lon: number
  presence_basis?: string | null
  attribution_flags?: string[]
  radius_m: number | null
  radius_basis: string
  start_utc: string
  end_utc: string
  source_app: string | null
  attribution_flags?: string[] | null
}

export interface PlacesResponse {
  total: number
  returned: number
  next_cursor: number | null
  page_size: number
  observations: PlaceObservation[]
  towers_not_placed: { words: string; reason: string; mcc_inferred?: boolean; mcc_words?: string | null }[]
  mcc_inferred_words?: string
  reverse_geocoding: { enabled: boolean; reason: string }
  label?: string
}

export interface RoutinePlaceRow {
  cluster_id: number
  lat: number
  lon: number
  radius_m: number
  stay_count: number
  day_count: number
  routine: boolean
  label: string | null
  place_id: string | null
  label_by: string | null
  first_utc: string
  last_utc: string
}

export interface RoutineResponse {
  parameters: Record<string, unknown>
  zone: string
  places: RoutinePlaceRow[]
  routine_places: number[]
  presence_days: number
  observations_used: number
  stays_total: number
  label: string
}

export interface DeviationResponse {
  threshold: number | null
  days_scored: number
  flagged: { date: string; score_bits: number; expectation: string; hours: { hour: number; place: number | "elsewhere" }[] }[]
  label: string
}

export interface ManualPlace {
  id: string
  lat: number
  lon: number
  radius_m: number
  reason: string
  decision_id: string
  removed_decision_id: string | null
  actor_name: string | null
  created_at: string
}

export interface Snapshot {
  id: string
  kind: "day" | "window" | "grid" | "places"
  label: string
  record_count: number
  stale: boolean
  stale_words: string | null
  snapshot: {
    summary_counts: Record<string, number>
    window: { start: string; end: string; zone: string }
    subject?: Subject | { kind: "case" }
    parameters?: Record<string, unknown>
  }
  created_by_name?: string | null
  created_at?: string
}

/** A saved statement check opened by its id alone (GET /checks/{id}): the check as it ran, with its statement. */
export type SavedCheck = Evaluation & { claim: Claim; subject: Subject }

export interface SnapshotRequest {
  kind: Snapshot["kind"]
  subject?: string
  date?: string
  start_date?: string
  end_date?: string
  start?: string
  end?: string
  zone?: string
  parameters?: Record<string, unknown>
}

export interface KeyDate {
  entry_id: string
  kind: "date" | "term"
  label: string
  instant_utc: string | null
  zone: string | null
  local: string | null
  term: string | null
  title: string
}

const base = (caseId: string) => `/api/pattern/${encodeURIComponent(caseId)}`
const subj = (s: Subject) => encodeURIComponent(JSON.stringify(s))

export const patternAPI = {
  subjects: (caseId: string) => fetchAPI<SubjectList>(`${base(caseId)}/subjects`),
  day: (caseId: string, s: Subject, date: string, zone = "device") =>
    fetchAPI<DayResponse>(`${base(caseId)}/day?subject=${subj(s)}&date=${date}&zone=${encodeURIComponent(zone)}`),
  window: (caseId: string, at: string, span: string, zone = "device") =>
    fetchAPI<WindowResponse>(`${base(caseId)}/window?at=${encodeURIComponent(at)}&span=${span}&zone=${encodeURIComponent(zone)}`),
  /** A window with its own start and end (a statement's window, 05 16.3). */
  windowCustom: (caseId: string, start: string, end: string, zone = "case") =>
    fetchAPI<WindowResponse>(`${base(caseId)}/window?span=custom&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&zone=${encodeURIComponent(zone)}`),
  /** The whole calendar day, in the zone, around an anchor with a date and no time (07 J-5). */
  windowDay: (caseId: string, day: string, zone = "case") =>
    fetchAPI<WindowResponse>(`${base(caseId)}/window?span=day&day=${encodeURIComponent(day)}&zone=${encodeURIComponent(zone)}`),
  grid: (caseId: string, s: Subject, start: string, end: string, zone = "device") =>
    fetchAPI<GridResponse>(`${base(caseId)}/grid?subject=${subj(s)}&start_date=${start}&end_date=${end}&zone=${encodeURIComponent(zone)}`),
  places: (caseId: string, s: Subject, start: string, end: string, cursor = 0) =>
    fetchAPI<PlacesResponse>(
      `${base(caseId)}/places?subject=${subj(s)}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&cursor=${cursor}`),
  routine: (caseId: string, s: Subject, zone = "device") =>
    fetchAPI<RoutineResponse>(`${base(caseId)}/routine?subject=${subj(s)}&zone=${encodeURIComponent(zone)}`),
  deviations: (caseId: string, s: Subject, zone = "device") =>
    fetchAPI<DeviationResponse>(`${base(caseId)}/routine/deviations?subject=${subj(s)}&zone=${encodeURIComponent(zone)}`),
  namePlace: (caseId: string, s: Subject, cluster_id: number, label: string, reason: string, zone = "device") =>
    fetchAPI<{ place_id: string; decision_id: string; label: string | null; previous_label: string | null }>(
      `${base(caseId)}/routine/places/name`,
      { method: "POST", body: { subject: JSON.stringify(s), cluster_id, label, reason, zone } as never }),
  manualPlaces: (caseId: string, transactionId: string) =>
    fetchAPI<{ total: number; items: ManualPlace[] }>(`${base(caseId)}/places/manual/${encodeURIComponent(transactionId)}`),
  attachPlace: (caseId: string, transactionId: string, lat: number, lon: number, radius_m: number, reason: string) =>
    fetchAPI<{ place_id: string; decision_id: string }>(`${base(caseId)}/places/manual`, { method: "POST",
      body: { target: { kind: "transaction", transaction_id: transactionId }, lat, lon, radius_m, reason } as never }),
  removePlace: (caseId: string, transactionId: string, reason: string) =>
    fetchAPI<{ decision_id: string }>(`${base(caseId)}/places/manual/remove`, { method: "POST",
      body: { target: { kind: "transaction", transaction_id: transactionId }, reason } as never }),
  together: (caseId: string, a: Subject, b: Subject, start: string, end: string) =>
    fetchAPI<TogetherResponse>(`${base(caseId)}/together`, { method: "POST", body: { subjects: [a, b], start, end } as never }),
  togetherRun: (caseId: string, runId: string, cursor = 0) =>
    fetchAPI<TogetherResponse>(`${base(caseId)}/together/${runId}?cursor=${cursor}`),
  claims: (caseId: string) => fetchAPI<{ total: number; items: Claim[] }>(`${base(caseId)}/claims`),
  createClaim: (caseId: string, fields: Record<string, unknown>) =>
    fetchAPI<Claim>(`${base(caseId)}/claims`, { method: "POST", body: fields as never }),
  editClaim: (caseId: string, id: string, fields: Record<string, unknown>, expected_version: number) =>
    fetchAPI<Claim>(`${base(caseId)}/claims/${id}`, { method: "PATCH", body: { fields, expected_version } as never }),
  confirmClaim: (caseId: string, id: string, expected_version: number) =>
    fetchAPI<Claim>(`${base(caseId)}/claims/${id}/confirm`, { method: "POST", body: { expected_version } as never }),
  evaluate: (caseId: string, id: string) =>
    fetchAPI<Evaluation>(`${base(caseId)}/claims/${id}/evaluate`, { method: "POST" }),
  evaluations: (caseId: string, id: string) =>
    fetchAPI<{ total: number; items: { evaluation_id: string; stale: boolean; outcome: string }[] }>(`${base(caseId)}/claims/${id}/evaluations`),
  evaluation: (caseId: string, id: string, eid: string) =>
    fetchAPI<Evaluation>(`${base(caseId)}/claims/${id}/evaluations/${eid}`),
  groupEvents: (caseId: string, id: string, eid: string, ordinal: number, cursor = 0) =>
    fetchAPI<GroupEvents>(`${base(caseId)}/claims/${id}/evaluations/${eid}/items/${ordinal}/events?cursor=${cursor}`),
  dispute: (caseId: string, id: string, eid: string, ordinal: number, reason: string) =>
    fetchAPI<{ dispute_id: string }>(`${base(caseId)}/claims/${id}/evaluations/${eid}/items/${ordinal}/dispute`,
      { method: "POST", body: { reason } as never }),
  keyDates: (caseId: string, kind?: "date" | "term") =>
    fetchAPI<{ total: number; items: KeyDate[] }>(`${base(caseId)}/key-dates${kind ? `?kind=${kind}` : ""}`),
  createKeyDate: (caseId: string, body: { kind: "date" | "term"; label: string; instant?: string; zone?: string; term?: string }) =>
    fetchAPI<KeyDate>(`${base(caseId)}/key-dates`, { method: "POST", body: body as never }),
  snapshot: (caseId: string, id: string) => fetchAPI<Snapshot>(`${base(caseId)}/snapshots/${encodeURIComponent(id)}`),
  check: (caseId: string, evaluationId: string) =>
    fetchAPI<SavedCheck>(`${base(caseId)}/checks/${encodeURIComponent(evaluationId)}`),
  freeze: (caseId: string, body: SnapshotRequest) =>
    fetchAPI<Snapshot>(`${base(caseId)}/snapshots`, { method: "POST", body: body as never }),
  addToInterview: (dossierId: string, interviewId: string, item: { target_type: string; target_id: string }) =>
    fetchAPI<{ added: number; already_there: number }>(
      `/api/dossiers/${encodeURIComponent(dossierId)}/interviews/${encodeURIComponent(interviewId)}/evidence:add`,
      { method: "POST", body: { ...item, source_anchor: {} } as never }),
  draft: (caseId: string, body: { dossier_id: string; subject: Subject; interview_ids?: string[]; conversation_locator?: string }) =>
    fetchAPI<{ id: string; job_status: string }>(`${base(caseId)}/claim-drafts`, { method: "POST", body: body as never }),
}
