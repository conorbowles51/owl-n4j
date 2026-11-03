import { ApiError, fetchAPI } from "@/lib/api-client"
import { z } from "zod"
import {
  ParticipantListSchema,
  ProfileSchema,
  PhonesSchema,
  RecordDetailSchema,
  ReviewSchema,
  StreamIndexSchema,
  StreamWindowSchema,
  ThreadListSchema,
  type RecordDetail,
  type ThreadList,
  type StreamIndex,
  type StreamWindow,
} from "./schemas"

/** Typed calls for the phone screens (03 sections 4 to 6). */

export interface StreamFilter {
  case_id: string
  phones?: string[]
  threads?: string[]
  participants?: string[]
  participant_mode?: "any" | "all" | "between" | "sent_by" | "sent_to"
  expand_person_identities?: boolean
  group_scope?: "direct" | "include_groups"
  apps?: string[]
  kinds?: ("message" | "call" | "email" | "voicemail" | "chat_activity")[]
  directions?: ("incoming" | "outgoing" | "unknown")[]
  deleted_states?: (string | null)[]
  flags?: { carved?: boolean | null; synced?: boolean | null; has_attachment?: boolean | null; unreadable?: boolean | null }
  from_instant?: string | null
  to_instant?: string | null
  include_no_time?: boolean
  text?: { query: string; exact_characters?: boolean }
  collapse_copies?: boolean
  names?: { mode: "phone" | "case" }
  zone?: { mode: "phone" | "case" | "utc"; phone?: string | null }
  sort?: "oldest_first" | "newest_first"
  /** A frozen phone selection's id: only its records (a saved link to a whole result, 07 6.1). */
  selection?: string
}

/** A window asked for under a snapshot the server no longer holds (3.1 rule 3). */
export class StaleSnapshotError extends Error {
  constructor() {
    super("stale_snapshot")
    this.name = "StaleSnapshotError"
  }
}

/** The 3.8 error wording with the reference a person can quote. */
export function failureText(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const d = (error.data as { detail?: { text?: string } } | undefined)?.detail
    if (d && typeof d === "object" && typeof d.text === "string") return d.text
  }
  return fallback
}

export async function getPhones(caseId: string) {
  return PhonesSchema.parse(await fetchAPI(`/api/phones?case_id=${encodeURIComponent(caseId)}`))
}

export async function streamIndex(filter: StreamFilter, signal?: AbortSignal): Promise<StreamIndex> {
  return StreamIndexSchema.parse(await fetchAPI("/api/phones/streams/index", { method: "POST", body: filter, read: true, signal }))
}

export async function streamWindow(
  filter: StreamFilter,
  snapshot: string,
  day: string | null,
  offset: number,
  limit: number,
  signal?: AbortSignal,
): Promise<StreamWindow> {
  try {
    return StreamWindowSchema.parse(
      await fetchAPI("/api/phones/streams/window", { method: "POST", body: { filter, snapshot, day, offset, limit }, read: true, signal }),
    )
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) throw new StaleSnapshotError()
    throw e
  }
}

export async function streamLocate(filter: StreamFilter, snapshot: string, eventUid: string): Promise<{ day: string | null; offset: number }> {
  try {
    return await fetchAPI("/api/phones/streams/locate", { method: "POST", body: { filter, snapshot, event_uid: eventUid }, read: true })
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) throw new StaleSnapshotError()
    throw e
  }
}

export async function getRecord(caseId: string, recordUid: string, zone?: string): Promise<RecordDetail> {
  const q = new URLSearchParams({ case_id: caseId })
  if (zone) q.set("zone", zone)
  return RecordDetailSchema.parse(await fetchAPI(`/api/phones/records/${encodeURIComponent(recordUid)}?${q}`))
}

/** One sensitive value in full; the server logs who revealed it, when, and which record and field first (05 3.8). */
export async function revealValue(caseId: string, recordUid: string, fieldPath: string, valueIndex: number) {
  return fetchAPI<{ value: string; logged: boolean }>(`/api/phones/records/${encodeURIComponent(recordUid)}/reveal`, {
    method: "POST",
    body: { case_id: caseId, field_path: fieldPath, value_index: valueIndex },
  })
}

export async function getSettings(caseId: string) {
  return fetchAPI<{ case_id: string; time_zone: string | null; effective: { name: string; basis: string; note: string | null }; updated_at: string | null; updated_by: string | null }>(
    `/api/phones/settings?case_id=${encodeURIComponent(caseId)}`,
  )
}

export async function putSettings(caseId: string, timeZone: string) {
  return fetchAPI(`/api/phones/settings`, { method: "PUT", body: { case_id: caseId, time_zone: timeZone } })
}

export type ThreadSort = "recent" | "first" | "volume" | "unreviewed" | "name"

/** Every thread under the filter, in one response (03 section 6.3). */
export async function getThreads(filter: StreamFilter, sort: ThreadSort = "recent"): Promise<ThreadList> {
  return ThreadListSchema.parse(
    await fetchAPI(`/api/phones/conversations/threads?sort=${sort}`, { method: "POST", body: filter, read: true }),
  )
}

/** People mode: every participant under the filter, in one response. */
export async function getParticipants(filter: StreamFilter) {
  return ParticipantListSchema.parse(await fetchAPI("/api/phones/conversations/participants", { method: "POST", body: filter, read: true }))
}

export async function markReviewed(caseId: string, threadKey: string, scope: Record<string, unknown> = {}) {
  const out = await fetchAPI<{ thread_key: string; review: unknown }>("/api/phones/conversations/review", {
    method: "POST",
    body: { case_id: caseId, thread_key: threadKey, scope },
  })
  return { thread_key: out.thread_key, review: ReviewSchema.parse(out.review) }
}

export async function undoReviewed(caseId: string, threadKey: string) {
  return fetchAPI<{ thread_key: string; restored: boolean }>("/api/phones/conversations/review/undo", {
    method: "POST",
    body: { case_id: caseId, thread_key: threadKey },
  })
}

/** A person's Not a copy decision on one record (03 section 3.4, C-13); `restore` puts it back in its group. */
export async function markNotACopy(caseId: string, recordUid: string, reason: string, restore = false) {
  return fetchAPI<{ decision_id: string; restored: boolean; groups: number }>(`/api/phones/records/${recordUid}/not-a-copy`, {
    method: "POST",
    body: { case_id: caseId, reason, restore },
  })
}

/** Freeze every record the filter matches now as one phone selection, for Add to… on a whole result (07 6.1). */
export interface SavedSelection {
  id: string
  words: string
  record_count: number
  event_count: number
  created_at: string | null
  replaced: string | null
}
export async function getSelection(caseId: string, id: string) {
  return fetchAPI<SavedSelection>(`/api/phones/selections/${encodeURIComponent(id)}?case_id=${encodeURIComponent(caseId)}`)
}
export async function freezeSelection(filter: StreamFilter, words: string) {
  return fetchAPI<{ id: string; record_count: number; event_count: number; words: string }>("/api/phones/selections", {
    method: "POST",
    body: { filter, words },
  })
}

/** Phone summary (03 section 7): every number a count over the read views, each with the list it opens. */
export async function getProfile(caseId: string, extractionId: string) {
  return ProfileSchema.parse(await fetchAPI(`/api/phones/${encodeURIComponent(extractionId)}/profile?case_id=${encodeURIComponent(caseId)}`, { read: true }))
}

/** Set whose phone this is (03 section 7.3): a set_phone_owner decision with the person's reason. */
const CompareCountsSchema = z.object({ both: z.number(), only_a: z.number(), only_a_outside: z.number(), only_b: z.number(), only_b_outside: z.number() })
const CompareSideSchema = z.object({ extraction_id: z.string(), label: z.string(), first: z.string().nullable(), last: z.string().nullable(), no_time: z.number() })
export const CompareSchema = z.object({
  case_id: z.string(),
  person: z.string().nullable(),
  a: CompareSideSchema,
  b: CompareSideSchema,
  kinds: z.object({ message: CompareCountsSchema, call: CompareCountsSchema }),
  key: z.string(),
})
export type PhoneComparison = z.infer<typeof CompareSchema>

export async function comparePhones(caseId: string, a: string, b: string, person?: string | null, signal?: AbortSignal) {
  const q = new URLSearchParams({ case_id: caseId, a, b })
  if (person) q.set("person", person)
  return CompareSchema.parse(await fetchAPI(`/api/phones/compare?${q}`, { signal }))
}

/** The other numbers and accounts linked to the same person (07 J-3 step 3). */
export async function getLinkedIdentities(caseId: string, key: string) {
  return fetchAPI<{ others: string[]; numbers: number; accounts: number }>(`/api/phones/people/linked?${new URLSearchParams({ case_id: caseId, key })}`)
}

export const ExportFactsSchema = z.object({
  total: z.number(), messages: z.number(), calls: z.number(), other: z.number(), unconfirmed: z.number(), phones: z.number(),
  collapsed_copies: z.number(), zone: z.string(), left_out: z.string(), limits: z.array(z.object({ message: z.string() }).passthrough()),
  /** Machine text on the attachments in scope (07 5 Media, M-7): confirm it or keep it marked before exporting. */
  machine_text: z.object({
    total: z.number(), unconfirmed: z.number(), items_cap: z.number(),
    items: z.array(z.object({ id: z.string(), file_uid: z.string(), kind: z.enum(["ocr", "transcript"]), filename: z.string().nullable(), words: z.string().nullable() })),
  }).optional(),
})
export const ExportStateSchema = z.object({
  export_id: z.string(), format: z.string(), source: z.string(), state: z.enum(["queued", "rendering", "done", "failed"]), progress: z.number(),
  counts: z.record(z.string(), z.unknown()), file: z.object({ filename: z.string().nullable(), size: z.number().nullable(), sha256: z.string().nullable() }).nullable(),
  error: z.string().nullable(), created_at: z.string().nullable(), finished_at: z.string().nullable(), title: z.string().nullable().optional(),
})
export type ExportState = z.infer<typeof ExportStateSchema>

/** What an export of this filter holds, before anything is drawn (03 section 12.2 steps 1 and 2). */
export async function describeExport(caseId: string, filter: StreamFilter) {
  return ExportFactsSchema.parse(await fetchAPI("/api/phones/exports/describe", { method: "POST", body: { case_id: caseId, filter }, read: true }))
}
export async function createExport(caseId: string, filter: StreamFilter, options: Record<string, unknown>, format: "pdf" | "rsmf" = "pdf") {
  return fetchAPI<{ export_id: string }>("/api/phones/exports", { method: "POST", body: { case_id: caseId, format, source: "stream", filter, options } })
}
export async function getExport(caseId: string, exportId: string) {
  return ExportStateSchema.parse(await fetchAPI(`/api/phones/exports/${encodeURIComponent(exportId)}?case_id=${encodeURIComponent(caseId)}`))
}
export async function getExportHistory(caseId: string) {
  return z.object({ items: z.array(ExportStateSchema) }).parse(await fetchAPI(`/api/phones/exports?case_id=${encodeURIComponent(caseId)}`))
}
/** Saves a finished export's file (the same signed-in fetch as the timeline export; a plain link carries no token). */
export async function downloadExport(caseId: string, exportId: string, filename: string) {
  const token = localStorage.getItem("authToken")
  const response = await fetch(`/api/phones/exports/${encodeURIComponent(exportId)}/file?case_id=${encodeURIComponent(caseId)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
  })
  if (!response.ok) throw new Error("The export file could not be fetched.")
  const url = URL.createObjectURL(await response.blob())
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function setPhoneLabel(caseId: string, extractionId: string, label: string, reason: string) {
  return fetchAPI<{ decision_id: string; label: string; before: string | null }>(`/api/phones/${encodeURIComponent(extractionId)}/label`, {
    method: "POST",
    body: { case_id: caseId, label, reason },
  })
}

export async function setOwner(caseId: string, extractionId: string, identityKey: string, reason: string) {
  return fetchAPI<{ decision_id: string; owner_identity_keys: string[] }>(`/api/phones/${encodeURIComponent(extractionId)}/owner`, {
    method: "POST",
    body: { case_id: caseId, identity_key: identityKey, reason },
  })
}

export const ExplanationSchema = z.object({
  entry_id: z.string(),
  heading: z.string(),
  has_phone_links: z.boolean(),
  links: z.object({ total: z.number(), by_type: z.record(z.string(), z.number()) }),
  scope: z.array(z.object({ kind: z.string(), words: z.string(), records: z.number().optional(), events: z.number().nullable().optional(), missing: z.boolean().optional() }).passthrough()).optional(),
  searches: z.array(z.object({ query: z.string(), exact: z.boolean() })).optional(),
  readings: z.object({ records: z.number(), confirmed: z.number(), unconfirmed: z.number(), as_recorded: z.number(), not_in_current_reading: z.number() }).optional(),
  identities: z.array(z.object({ identity: z.string(), decisions: z.number(), linked_to_person: z.boolean(), missing: z.boolean() })).optional(),
  assumptions: z.array(z.object({ phone: z.string().nullable(), code: z.string(), words: z.string() })).optional(),
  label: z.string().optional(),
  label_reasons: z.array(z.string()).optional(),
})
export type Explanation = z.infer<typeof ExplanationSchema>

/** How this was found (07 J-17): generated from a finding's phone links. */
export async function getFindingExplanation(caseId: string, entryId: string, signal?: AbortSignal) {
  return ExplanationSchema.parse(await fetchAPI(`/api/phones/findings/${encodeURIComponent(entryId)}/explain?${new URLSearchParams({ case_id: caseId })}`, { signal }))
}

export interface PhoneMapFilter {
  phones?: string[]
  source_kinds?: string[]
  affiliations?: string[]
  from_instant?: string | null
  to_instant?: string | null
  include_no_time?: boolean
}
export const PhoneMapSummarySchema = z.object({
  case_id: z.string(),
  positioned: z.number(),
  total: z.number(),
  not_positionable: z.array(z.object({ reason: z.string(), model_type: z.string(), count: z.number(), phones: z.number() })),
  by_source: z.record(z.string(), z.number()),
  bbox: z.array(z.number()).length(4).nullable(),
})
const PhoneMapPointSchema = z.object({
  type: z.literal("point"), point_uid: z.string(), record_uid: z.string(), extraction_id: z.string(), phone_label: z.string(),
  lat: z.number(), lon: z.number(), accuracy_m: z.number().nullable(), accuracy_words: z.string(), source_words: z.string(),
  affiliation: z.string().nullable(), instant: z.string().nullable(), time: z.object({ full: z.string() }).passthrough().nullable(),
  model_type: z.string(), flags: z.array(z.string()), deleted_state: z.string().nullable(),
})
const PhoneMapClusterSchema = z.object({ type: z.literal("cluster"), lat: z.number(), lon: z.number(), count: z.number(), bbox: z.array(z.number()) })
export const PhoneMapPointsSchema = z.object({
  case_id: z.string(), total: z.number(), clustered: z.boolean(),
  items: z.array(z.union([PhoneMapPointSchema, PhoneMapClusterSchema])),
  limits: z.array(z.object({ message: z.string() }).passthrough()),
})
export type PhoneMapSummary = z.infer<typeof PhoneMapSummarySchema>
export type PhoneMapPoints = z.infer<typeof PhoneMapPointsSchema>
export type PhoneMapItem = PhoneMapPoints["items"][number]

/** The Map phone layer (03 section 13.2): never through /api/graph/locations. */
export async function getPhoneMapSummary(caseId: string, filter: PhoneMapFilter = {}, signal?: AbortSignal) {
  return PhoneMapSummarySchema.parse(await fetchAPI("/api/phones/map/summary", { method: "POST", body: { case_id: caseId, filter }, read: true, signal }))
}
export async function getPhoneMapPoints(caseId: string, bbox: number[], zoom: number, filter: PhoneMapFilter = {}, signal?: AbortSignal) {
  return PhoneMapPointsSchema.parse(await fetchAPI("/api/phones/map/points", { method: "POST", body: { case_id: caseId, bbox, zoom, filter }, read: true, signal }))
}

export interface MediaFilter {
  case_id: string
  phones?: string[]
  categories?: string[]
  verification?: string[]
  linked_to_message?: boolean | null
}
export interface MediaIndex { total: number; no_time_count: number; missing: number; by_category: Record<string, number>; verification: Record<string, number> }
export interface MediaItem {
  file_uid: string; extraction_id: string; phone_label: string; category: string | null; filename: string; size: number | null
  taken_or_sent: { instant: string | null; full: string; basis: string }
  verification: string | null; verification_words: string; missing: boolean; deleted_state: string | null; is_carved: boolean
  message_count: number; thumbnail_url: string | null
  /** The machine text in use for each kind, with its one origin mark (07 4.6); null when there is none. */
  machine_text?: { kind: "ocr" | "transcript"; state: "machine" | "confirmed" | "corrected" | "pending"; short: string; words: string | null }[] | null
}
export interface MediaDetail {
  file_uid: string; extraction_id: string; category: string | null; local_path: string | null; size: number | null
  hashes: Record<string, string | null>; verification: string | null; verification_words: string; missing: boolean
  missing_words: string | null; deleted_state: string | null; is_carved: boolean; message_count: number
  messages: { record_uid: string; message_record_uid: string; kind: string | null; instant: string | null; mechanism: string; mechanism_words: string }[]
}

/** Media (03 section 8.2). */
export async function getMediaIndex(filter: MediaFilter) {
  return fetchAPI<MediaIndex>("/api/phones/media/index", { method: "POST", body: filter, read: true })
}
export async function getMediaWindow(filter: MediaFilter, offset: number, limit = 200) {
  return fetchAPI<{ items: MediaItem[]; offset: number; limit: number }>("/api/phones/media/window", { method: "POST", body: { filter, offset, limit }, read: true })
}
/** Machine-generated text from a photo or audio (03 8.3, M-3): made by a model on the server, never by a person. */
export interface DerivedText {
  id: string; file_uid: string; kind: "ocr" | "transcript"; state: "queued" | "running" | "done" | "failed"
  text: string | null; model: string | null; model_version: string | null
  segments: { start: number; end: number; text: string }[]; error: string | null
  created_at: string | null; finished_at: string | null; machine_generated: true; label: string | null
  /** What made it (05 17.4): null on texts made before this was recorded. */
  model_id?: string | null; weights_sha256?: string | null; input_sha256?: string | null
  parameters?: Record<string, unknown> | null; provider?: string | null; provider_words?: string | null
  language?: string | null; duration_seconds?: number | null; sniffed_container?: string | null
  /** A person's correction or confirmation (07 4.6). The machine text stays in `text` and stays shown. */
  corrected_text?: string | null; correction_reason?: string | null; corrected_by?: string | null; corrected_at?: string | null
  confirmed_by?: string | null; confirmed_at?: string | null; effective_text?: string | null
  /** The reading search, the PDF and assessments use for this file and kind: a person's latest, else the latest. */
  in_use?: boolean
  origin?: { state: "pending" | "machine" | "confirmed" | "corrected"; words: string | null; confirmed: boolean }
}
export async function correctDerivedText(caseId: string, derivedId: string, text: string, reason: string) {
  return fetchAPI<{ id: string; decision_id: string }>(`/api/phones/media/derived/${encodeURIComponent(derivedId)}/correct`, { method: "POST", body: { case_id: caseId, text, reason } })
}
/** Batch reading of a Media scope (07 5 Media, M-5): true counts by state, from the server. */
export interface DeriveBatchFacts {
  kind: "ocr" | "transcript"; in_scope: number; eligible: number; noun: string
  left_out: { already_read: number; not_in_production: number; empty_placeholder: number; uncategorised?: number }
}
export interface DeriveBatch {
  id: string; kind: "ocr" | "transcript"; scope_words: string | null; total: number; done: number; failed: number
  queued: number; running: number; cancelled: boolean; cancelled_count: number; state: "running" | "done" | "cancelled"
  created_at: string; first_started_at: string | null; last_finished_at: string | null; noun: string
  left_out: { already_read?: number; not_in_production?: number; empty_placeholder?: number }
}
const batchFilter = (f: MediaFilter) => { const { case_id: _drop, ...rest } = f; void _drop; return rest }
export async function describeDeriveBatch(filter: MediaFilter, kind: "ocr" | "transcript") {
  return fetchAPI<DeriveBatchFacts>("/api/phones/media/derive-batches/describe", { method: "POST", body: { case_id: filter.case_id, kind, filter: batchFilter(filter) }, read: true })
}
export async function createDeriveBatch(filter: MediaFilter, kind: "ocr" | "transcript", scopeWords: string) {
  return fetchAPI<DeriveBatch>("/api/phones/media/derive-batches", { method: "POST", body: { case_id: filter.case_id, kind, filter: batchFilter(filter), scope_words: scopeWords } })
}
export async function getDeriveBatches(caseId: string) {
  return fetchAPI<{ case_id: string; items: DeriveBatch[] }>(`/api/phones/media/derive-batches?case_id=${encodeURIComponent(caseId)}`)
}
export async function cancelDeriveBatch(caseId: string, batchId: string) {
  return fetchAPI<DeriveBatch>(`/api/phones/media/derive-batches/${encodeURIComponent(batchId)}/cancel?case_id=${encodeURIComponent(caseId)}`, { method: "POST" })
}
export async function acceptDerivedText(caseId: string, derivedId: string, dossierId: string, category: string) {
  return fetchAPI<{ id: string; read_by: string | null }>(`/api/phones/media/derived/${encodeURIComponent(derivedId)}/accept-into-assessment`, { method: "POST", body: { case_id: caseId, dossier_id: dossierId, category } })
}
export async function confirmDerivedText(caseId: string, derivedId: string, note = "") {
  return fetchAPI<{ id: string; decision_id: string }>(`/api/phones/media/derived/${encodeURIComponent(derivedId)}/confirm`, { method: "POST", body: { case_id: caseId, note } })
}
export async function getDerivedTexts(caseId: string, fileUid: string) {
  return fetchAPI<{ file_uid: string; items: DerivedText[] }>(`/api/phones/media/${encodeURIComponent(fileUid)}/derived?case_id=${encodeURIComponent(caseId)}`)
}
export async function requestDerivedText(caseId: string, fileUid: string, kind: "ocr" | "transcript") {
  return fetchAPI<DerivedText>(`/api/phones/media/${encodeURIComponent(fileUid)}/derive`, { method: "POST", body: { case_id: caseId, kind } })
}
export async function getMediaDetail(caseId: string, fileUid: string) {
  return fetchAPI<MediaDetail>(`/api/phones/media/${encodeURIComponent(fileUid)}?case_id=${encodeURIComponent(caseId)}`)
}
/** A phone file's bytes as an object URL (the bearer token cannot ride on an <img src>). The caller revokes it. */
export async function mediaObjectUrl(caseId: string, fileUid: string, signal?: AbortSignal, variant: "content" | "thumbnail" | "converted" = "content") {
  const token = localStorage.getItem("authToken")
  // the Media grid asks for a small preview made on the server; the viewer asks for the original, and for a
  // converted copy (H.264/AAC, made on the server) only when the browser cannot play the original
  const response = await fetch(`/api/phones/media/${encodeURIComponent(fileUid)}/${variant}?case_id=${encodeURIComponent(caseId)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
    signal,
  })
  if (!response.ok) {
    let words = "This file could not be shown."
    try {
      words = ((await response.json()) as { detail?: string }).detail ?? words
    } catch {
      /* not JSON */
    }
    throw new Error(words)
  }
  return { url: URL.createObjectURL(await response.blob()), type: response.headers.get("Content-Type") ?? "" }
}
