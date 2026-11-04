import { fetchAPI } from "@/lib/api-client"

/** Text places (04 section 6.5): routers/pattern_of_life.py get_text_places and the routes beside it. */
export interface TextPlacement {
  id: string
  lat: number
  lon: number
  radius_m: number
  reason: string
  suggestion: Suggestion | null
  decision_id: string
  actor_name: string | null
  created_at: string
  place_text: string
}

export interface TextPlace {
  extraction_id: string
  record_uid: string
  field_path: string
  model_type: string
  group: "calendar" | "checkin" | "other"
  group_words: string
  kind: "planned" | "declared" | "searched"
  kind_words: string
  place_text: string
  phone_text: string
  corrected: boolean
  start_utc: string | null
  end_utc: string | null
  placement: TextPlacement | null
  decisions: number
}

export interface SuggestionStatus { enabled: boolean; reason: string; places: number }

export interface TextPlaceList {
  total: number
  returned: number
  cursor: number
  limit: number
  next_cursor: number | null
  items: TextPlace[]
  counts: { all: number; placed: number; not_placed: number; by_group: Record<string, number> }
  status: string
  suggestions: SuggestionStatus
}

export interface Suggestion {
  geonameid: number | string
  name: string
  lat: number | string
  lon: number | string
  country_code: string | null
  country?: string | null
  admin1: string | null
  population: number | string | null
  matched?: string
}

export interface SuggestionList {
  enabled: boolean
  reason: string
  total: number
  returned: number
  label?: string
  attribution?: string
  candidates: Suggestion[]
}

export interface TextPlaceHistoryRow {
  id: string
  place_text: string
  lat: number
  lon: number
  radius_m: number
  reason: string
  suggestion: Suggestion | null
  decision_id: string
  removed_decision_id: string | null
  actor_name: string | null
  created_at: string
}

const base = (caseId: string) => `/api/pattern/${encodeURIComponent(caseId)}/text-places`
const target = (recordUid: string, fieldPath: string) =>
  `record_uid=${encodeURIComponent(recordUid)}&field_path=${encodeURIComponent(fieldPath)}`

export const textPlacesAPI = {
  list: (caseId: string, extractionId: string, cursor = 0) =>
    fetchAPI<TextPlaceList>(`${base(caseId)}?extraction_id=${encodeURIComponent(extractionId)}&cursor=${cursor}`),
  suggestions: (caseId: string, recordUid: string, fieldPath: string) =>
    fetchAPI<SuggestionList>(`${base(caseId)}/suggestions?${target(recordUid, fieldPath)}`),
  history: (caseId: string, recordUid: string, fieldPath: string) =>
    fetchAPI<{ total: number; items: TextPlaceHistoryRow[] }>(`${base(caseId)}/history?${target(recordUid, fieldPath)}`),
  place: (caseId: string, body: { record_uid: string; field_path: string; lat: number; lon: number; radius_m: number;
    reason: string; suggestion?: Suggestion | null }) =>
    fetchAPI<{ placement_id: string; decision_id: string }>(base(caseId), { method: "POST", body: body as never }),
  remove: (caseId: string, body: { record_uid: string; field_path: string; reason: string }) =>
    fetchAPI<{ decision_id: string }>(`${base(caseId)}/remove`, { method: "POST", body: body as never }),
}
