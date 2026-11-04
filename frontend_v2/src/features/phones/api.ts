import { ApiError, fetchAPI } from "@/lib/api-client"
import { z } from "zod"
import {
  ParticipantListSchema,
  ProfileSchema,
  PhonesSchema,
  RecordDetailSchema,
  SourceDatabaseSchema,
  type SourceDatabase,
  ReviewSchema,
  StreamIndexSchema,
  StreamWindowSchema,
  ThreadListSchema,
  TranslationSchema,
  type RecordDetail,
  type ThreadList,
  type StreamIndex,
  type StreamWindow,
} from "./schemas"
import { lazySchema } from "@/lib/lazy-schema"

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

/** Find in these results (03 section 3.1 rule 4): every match in the whole result, in list order, with the total. */
export async function streamFind(filter: StreamFilter, snapshot: string, query: string, exact = false): Promise<{ total: number; matches: { day: string | null; offset: number; event_uid: string }[] }> {
  try {
    return await fetchAPI("/api/phones/streams/find", { method: "POST", body: { filter, snapshot, query, exact }, read: true })
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

/** Correct this value (03 section 3.6, 02 section 10.4): a correct_phone_value decision with the person's reason; the
 * original stays recorded and shown beside the corrected value. */
export async function correctRecordValue(
  caseId: string,
  recordUid: string,
  body: { field_path: string; value_index: number; corrected_text: string; reason: string; expected_revision?: string },
) {
  return fetchAPI<Record<string, unknown>>(`/api/phones/records/${encodeURIComponent(recordUid)}/corrections`, {
    method: "POST",
    body: { case_id: caseId, ...body },
  })
}

/** Used in this case (03 section 3.6 item 8, 07 section 6.5): the reverse lookup of one record's collections. */
export async function getRecordUses(caseId: string, recordUid: string) {
  const r = await fetchAPI<{
    results: { target_id: string; summary: string | null; counts: Record<string, number>; uses: { kind: string; container_id: string; container_label: string | null; via: string; relationship: string | null }[] }[]
  }>(`/api/workspace/${encodeURIComponent(caseId)}/collections?target_type=phone_record&target_ids[]=${encodeURIComponent(recordUid)}`, { read: true })
  return r.results[0] ?? { target_id: recordUid, summary: null, counts: {}, uses: [] }
}

/** 05 section 17.2: the app database the report names as this record's source, read-only; ``browse`` pages a table. */
export async function getSourceDatabase(caseId: string, recordUid: string, source: number, browse?: string, page = 1): Promise<SourceDatabase> {
  const q = new URLSearchParams({ case_id: caseId, source: String(source), page: String(page) })
  if (browse) q.set("browse", browse)
  return SourceDatabaseSchema.parse(await fetchAPI(`/api/phones/records/${encodeURIComponent(recordUid)}/source-database?${q}`))
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
/** Save this view (07 section 6): the filter kept as a phone_view held by a new Workspace note. */
export interface SavedView {
  id: string
  words: string
  location: string
  event_count_then: number
  event_count_now: number
  created_at: string | null
  sentence: string
  replaced: string | null
}
export async function saveView(filter: StreamFilter, location: string, words: string) {
  return fetchAPI<{ id: string; entry_id: string; event_count: number; words: string }>("/api/phones/views", {
    method: "POST",
    body: { filter, location, words },
  })
}
export async function getSavedView(caseId: string, id: string) {
  return fetchAPI<SavedView>(`/api/phones/views/${encodeURIComponent(id)}?case_id=${encodeURIComponent(caseId)}`)
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
const CompareCountsSchema = lazySchema(() => z.object({ both: z.number(), only_a: z.number(), only_a_outside: z.number(), only_b: z.number(), only_b_outside: z.number() }))
const CompareSideSchema = lazySchema(() => z.object({ extraction_id: z.string(), label: z.string(), first: z.string().nullable(), last: z.string().nullable(), no_time: z.number() }))
export const CompareSchema = lazySchema(() => z.object({
  case_id: z.string(),
  person: z.string().nullable(),
  a: CompareSideSchema,
  b: CompareSideSchema,
  kinds: z.object({ message: CompareCountsSchema, call: CompareCountsSchema }),
  key: z.string(),
}))
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

export const ExportFactsSchema = lazySchema(() => z.object({
  total: z.number(), messages: z.number(), calls: z.number(), other: z.number(), unconfirmed: z.number(), phones: z.number(),
  collapsed_copies: z.number(), zone: z.string(), left_out: z.string(), sensitive_values: z.number().optional(), limits: z.array(z.object({ message: z.string() }).passthrough()),
  /** Machine text on the attachments in scope (07 5 Media, M-7): confirm it or keep it marked before exporting. */
  machine_text: z.object({
    total: z.number(), unconfirmed: z.number(), items_cap: z.number(),
    items: z.array(z.object({ id: z.string(), file_uid: z.string(), kind: z.enum(["ocr", "transcript"]), filename: z.string().nullable(), words: z.string().nullable() })),
  }).optional(),
  /** The Timeline phone lens only: the device events and sensor readings it is not showing, in words (T-7). */
  hidden: z.string().nullable().optional(),
}))
export const ExportStateSchema = lazySchema(() => z.object({
  export_id: z.string(), format: z.string(), source: z.string(), state: z.enum(["queued", "rendering", "done", "failed"]), progress: z.number(),
  counts: z.record(z.string(), z.unknown()), file: z.object({ filename: z.string().nullable(), size: z.number().nullable(), sha256: z.string().nullable() }).nullable(),
  error: z.string().nullable(), created_at: z.string().nullable(), finished_at: z.string().nullable(), title: z.string().nullable().optional(),
  // the phones of the export's filter (history only); none means every phone in the case
  phones: z.array(z.string()).optional(),
  whole_case: z.boolean().optional(),
}))
export type ExportState = z.infer<typeof ExportStateSchema>

/** What an export of this filter holds, before anything is drawn (03 section 12.2 steps 1 and 2). */
export type ExportSource = "stream" | "timeline_lens" | "collection" | "finding" | "dossier" | "analysis_result" | "statement_check" | "incident_window" | "phone_profile"
/** `source` "timeline_lens": the filter is the Timeline phone lens's and the totals are the lens's. */
export async function describeExport(caseId: string, filter: StreamFilter, source: ExportSource = "stream") {
  const body = source === "timeline_lens" ? { case_id: caseId, filter, source } : { case_id: caseId, filter }
  return ExportFactsSchema.parse(await fetchAPI("/api/phones/exports/describe", { method: "POST", body, read: true }))
}
export async function createExport(caseId: string, filter: StreamFilter, options: Record<string, unknown>, format: "pdf" | "rsmf" = "pdf", source: ExportSource = "stream") {
  return fetchAPI<{ export_id: string }>("/api/phones/exports", { method: "POST", body: { case_id: caseId, format, source, filter, options } })
}
/** A finding, theory or note's phone records frozen as one selection to export (07 XF-7, CO-12): the export's total
 * is `collected`; `sentence` names what of the entry is not in the export. */
export async function prepareEntryExport(caseId: string, entryId: string) {
  return fetchAPI<{ selection_id: string; filter: StreamFilter; collected: number; events: number; words: string; sentence: string | null }>(
    "/api/phones/exports/entry", { method: "POST", body: { case_id: caseId, entry_id: entryId } })
}
/** The records behind an analysis result (or a kept one), a statement check or an incident window frozen as one
 * selection to export (07 J-14b); `sentence` says what behind it is not a message or call and so not in the export. */
export async function prepareSourceExport(caseId: string, source: "analysis_result" | "statement_check" | "incident_window" | "collection" | "dossier", ref: Record<string, unknown>) {
  return fetchAPI<{ selection_id: string; filter: StreamFilter; collected: number; members?: number; events: number; words: string; sentence: string | null }>(
    "/api/phones/exports/source", { method: "POST", body: { case_id: caseId, source, ref } })
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

/** Accept the difference (07 J-1): an accept_phone_reconciliation_difference decision; the held reading resumes. */
export async function acceptReconciliationDifference(caseId: string, extractionId: string, reason: string) {
  return fetchAPI<{ decision_id: string; differences: number; restart: { state: string; words: string } }>(
    `/api/phones/${encodeURIComponent(extractionId)}/reconciliation/accept`,
    { method: "POST", body: { case_id: caseId, reason } },
  )
}

/** Since you last looked (03 section 7.3, 07 J-15): counts per change kind after the viewer's last visit. */
export async function getSinceLastLooked(caseId: string, extractionId: string, since: string) {
  const q = new URLSearchParams({ case_id: caseId, since })
  return fetchAPI<{ since: string; counts: Record<string, number | boolean>; lines: string[]; nothing: boolean }>(
    `/api/phones/${encodeURIComponent(extractionId)}/since?${q}`,
    { read: true },
  )
}

export async function setOwner(caseId: string, extractionId: string, identityKey: string, reason: string) {
  return fetchAPI<{ decision_id: string; owner_identity_keys: string[] }>(`/api/phones/${encodeURIComponent(extractionId)}/owner`, {
    method: "POST",
    body: { case_id: caseId, identity_key: identityKey, reason },
  })
}

export const ExplanationSchema = lazySchema(() => z.object({
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
}))
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
export const PhoneMapSummarySchema = lazySchema(() => z.object({
  case_id: z.string(),
  positioned: z.number(),
  total: z.number(),
  not_positionable: z.array(z.object({ reason: z.string(), model_type: z.string(), count: z.number(), phones: z.number() })),
  by_source: z.record(z.string(), z.number()),
  bbox: z.array(z.number()).length(4).nullable(),
}))
const PhoneMapPointSchema = lazySchema(() => z.object({
  type: z.literal("point"), point_uid: z.string(), record_uid: z.string(), extraction_id: z.string(), phone_label: z.string(),
  lat: z.number(), lon: z.number(), accuracy_m: z.number().nullable(), accuracy_words: z.string(), source_words: z.string(),
  affiliation: z.string().nullable(), instant: z.string().nullable(), time: z.object({ full: z.string() }).passthrough().nullable(),
  model_type: z.string(), flags: z.array(z.string()), deleted_state: z.string().nullable(),
}))
const PhoneMapClusterSchema = lazySchema(() => z.object({ type: z.literal("cluster"), lat: z.number(), lon: z.number(), count: z.number(), bbox: z.array(z.number()) }))
export const PhoneMapPointsSchema = lazySchema(() => z.object({
  case_id: z.string(), total: z.number(), clustered: z.boolean(),
  items: z.array(z.union([PhoneMapPointSchema, PhoneMapClusterSchema])),
  limits: z.array(z.object({ message: z.string() }).passthrough()),
}))
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

/** Show on Map from a message (03 section 3.6 item 7): the positions on the same phone within the hour of it. */
export const PhoneMapNearSchema = lazySchema(() => z.object({
  record_uid: z.string(),
  extraction_id: z.string(),
  instant: z.string().nullable(),
  window_minutes: z.number(),
  within: z.number(),
  from_instant: z.string().nullable(),
  to_instant: z.string().nullable(),
  bbox: z.array(z.number()).nullable(),
  nearest: z.object({ point_uid: z.string(), lat: z.number(), lon: z.number(), instant: z.string().nullable(), gap_seconds: z.number(), gap_words: z.string() }).nullable(),
  words: z.string(),
}))
export type PhoneMapNear = z.infer<typeof PhoneMapNearSchema>
export async function getPhoneMapNear(caseId: string, recordUid: string, signal?: AbortSignal) {
  const q = new URLSearchParams({ case_id: caseId, record_uid: recordUid })
  return PhoneMapNearSchema.parse(await fetchAPI(`/api/phones/map/near?${q}`, { signal }))
}

/** A thread header's attachment counts (03 section 6.7): "14 attachments referenced, 3 not in the report". */
export const ThreadAttachmentsSchema = lazySchema(() => z.object({
  thread_key: z.string(),
  referenced: z.number(),
  files: z.number(),
  not_in_report: z.number(),
  in_folders_only: z.number(),
  not_in_production: z.number(),
  words: z.string(),
}))
export async function getThreadAttachments(caseId: string, threadKey: string) {
  const q = new URLSearchParams({ case_id: caseId, thread_key: threadKey })
  return ThreadAttachmentsSchema.parse(await fetchAPI(`/api/phones/threads/attachments?${q}`))
}

export interface PhoneMapArea {
  case_id: string
  phones: { extraction_id: string; phone_label: string; points: number; points_without_time: number; first: string | null; last: string | null }[]
  phones_total: number
  points_total: number
  points_without_time: number
  window: { from_instant: string | null; to_instant: string | null }
  label: string
}

/** Phones seen in a drawn area (03 13.3, 07 J-10): every phone with a position inside, counted exactly. */
export async function getPhoneMapArea(caseId: string, ring: number[][], filter: PhoneMapFilter = {}, signal?: AbortSignal) {
  return fetchAPI<PhoneMapArea>("/api/phones/map/area", { method: "POST", body: { case_id: caseId, ring, filter }, read: true, signal })
}

export interface MediaFilter {
  case_id: string
  phones?: string[]
  categories?: string[]
  verification?: string[]
  linked_to_message?: boolean | null
  thread_key?: string
}
export interface MediaIndex { total: number; no_time_count: number; no_message_count?: number; missing: number; by_category: Record<string, number>; verification: Record<string, number> }
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
/** Media spread across phones, exact tier (05 section 11): the same file (equal MD5) on two or more phones. */
export interface SpreadPhoneRef { extraction_id: string; label: string }
export interface SpreadIndex {
  case_id: string; case_phone_count: number; total_groups: number; total_copies: number; common_file_groups: number
  sha256_disagreement_groups: number; by_phone: (SpreadPhoneRef & { groups: number })[]
  by_pair: { a: SpreadPhoneRef; b: SpreadPhoneRef; groups: number }[]; population_words: string; clock_words: string
}
export interface SpreadTime { source: "message_time" | "file_modified" | "exif_capture"; source_words: string; field: string; instant: string | null; full: string; has_offset: boolean }
export interface SpreadCopy {
  file_uid: string; extraction_id: string; phone_label: string; filename: string; local_path: string | null; original_path: string | null
  category: string | null; size: number | null; sha256: string | null; verification: string | null; verification_words: string; missing: boolean
  included_because: string[]; times: SpreadTime[]; earliest: SpreadTime | null; roles: string[]
  messages: { message_record_uid: string; kind: string | null; direction: string | null; role: string; instant: string | null; full: string; app: string | null; deleted: boolean; line: string | null }[]
  note: string | null; camera: { make: string | null; model: string | null } | null; in_camera_folder: boolean
  camera_original_candidate: boolean | null; camera_original_words: string | null
  place: { latitude: string | null; longitude: string | null; combined: string | null; source: string; words: string } | null
}
export interface SpreadPhone {
  extraction_id: string; phone_label: string; position: number | null; earliest: SpreadTime | null; roles: string[]
  camera_original_candidate: boolean; copy_count: number; copies_shown: number; copies_words: string | null; copies: SpreadCopy[]
}
export interface SpreadGroup {
  group_key: string; md5: string; phone_count: number; copy_count: number; phones_with_hash: number; case_phone_count: number
  common_file: boolean; common_words: string | null; sha256_disagrees: boolean; sha256_words: string | null
  category: string | null; filename: string; size: number | null; thumbnail_file_uid: string | null
  clock_offset_unknown: boolean; clock_words: string; camera_original_candidates: number; phones: SpreadPhone[]; tier: "exact"
}
export interface SpreadFilter { phones?: string[]; common?: "all" | "hide" | "only" }
export async function getMediaSpreadIndex(caseId: string) {
  return fetchAPI<SpreadIndex>(`/api/phones/media-spread/index?case_id=${encodeURIComponent(caseId)}`)
}
export async function getMediaSpreadWindow(caseId: string, filter: SpreadFilter, offset: number, limit = 50) {
  const q = new URLSearchParams({ case_id: caseId, common: filter.common ?? "all", offset: String(offset), limit: String(limit) })
  for (const p of filter.phones ?? []) q.append("phones", p)
  return fetchAPI<{ case_id: string; total: number; offset: number; limit: number; items: SpreadGroup[]; clock_words: string }>(`/api/phones/media-spread/window?${q.toString()}`)
}
/** Near-identical pictures across phones, perceptual tier (05 section 11.3 step 3): graded pairs, never "identical". */
export interface PerceptualCopy {
  file_uid: string; extraction_id: string; phone_label: string; md5: string; filename: string; category: string | null
  copies_on_phone: number; roles: string[]; messages_total: number
  messages: { message_record_uid: string; role: string; full: string; app: string | null; deleted: boolean }[]
}
export interface PerceptualPair {
  level: "strong" | "moderate" | "weak" | "faint"; distance: number; phash_distance: number; dhash_distance: number; simple: boolean
  a: PerceptualCopy; b: PerceptualCopy; reasons: { match: string[]; substantiation: string[] }; label: string
}
export interface PerceptualPage {
  case_id: string; tier: "perceptual"; total: number; offset: number; limit: number; items: PerceptualPair[]
  by_strength: Record<string, number>; total_all: number; pictures_compared: number; stopped_words: string | null
  words: string; rule_words: string; clock_words: string
  hashing: { pictures: number; hashed: number; failed: number; waiting: number; failed_by_reason: Record<string, number>; failed_words: Record<string, string>; case_phones: number; not_hashed_words: string | null }
}
export async function getMediaSpreadPerceptual(caseId: string, strength: string | null, offset: number, limit = 50) {
  const q = new URLSearchParams({ case_id: caseId, offset: String(offset), limit: String(limit) })
  if (strength) q.set("strength", strength)
  return fetchAPI<PerceptualPage>(`/api/phones/media-spread/perceptual?${q.toString()}`)
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
/** Image search by description (05 17.6): a case's images indexed and ranked by a model on this server. */
export interface ImageIndexFacts {
  images: number; eligible: number; indexed: number; indexed_contents: number; waiting: number
  left_out: { not_in_population: number; not_in_production: number; empty_placeholder: number; could_not_open: number; could_not_open_by_reason: Record<string, number> }
  uncategorised_files: number; model_installed: boolean; model_words: string | null
  model: string | null; model_id: string | null; revision_short: string | null; population_words: string
}
export interface ImageIndexJob {
  id: string; total: number; done: number; embedded: number; reused: number; failed: number
  failed_by_reason: Record<string, number>; queued: number; running: number; cancelled: boolean; cancelled_count: number
  state: "running" | "done" | "cancelled"; created_at: string; first_started_at: string | null; last_finished_at: string | null; noun: string
}
export interface ImageSearchCopy { file_uid: string; extraction_id: string; phone_label: string; filename: string; category: string | null; message_count: number }
export interface ImageSearchResults {
  query: string; label: string; model: string; model_id: string; revision_short: string; provider_words: string
  /** distinct pictures ranked, and the indexed files holding them (the same files as the coverage count) */
  scored: number; scored_files: number; shown: number; coverage: ImageIndexFacts; truncated_query: boolean; truncated_words?: string | null
  results: { rank: number; content_sha256: string; copy_count: number; copies: ImageSearchCopy[]; phones: string[] }[]
}
export async function describeImageIndex(caseId: string) {
  return fetchAPI<ImageIndexFacts>("/api/phones/media/image-index/describe", { method: "POST", body: { case_id: caseId }, read: true })
}
export async function createImageIndex(caseId: string) {
  return fetchAPI<ImageIndexJob>("/api/phones/media/image-index", { method: "POST", body: { case_id: caseId } })
}
export async function getImageIndexJobs(caseId: string) {
  return fetchAPI<{ case_id: string; items: ImageIndexJob[] }>(`/api/phones/media/image-index?case_id=${encodeURIComponent(caseId)}`)
}
export async function cancelImageIndex(caseId: string, jobId: string) {
  return fetchAPI<ImageIndexJob>(`/api/phones/media/image-index/${encodeURIComponent(jobId)}/cancel?case_id=${encodeURIComponent(caseId)}`, { method: "POST" })
}
export async function searchImages(caseId: string, query: string, limit = 24) {
  return fetchAPI<ImageSearchResults>("/api/phones/media/image-search", { method: "POST", body: { case_id: caseId, query, limit }, read: true })
}
/** Machine translation on this server (05 17.5): one message, one machine text, or every message of a conversation. */
export async function translateMessage(caseId: string, eventUid: string) {
  return TranslationSchema.parse(await fetchAPI(`/api/phones/messages/${encodeURIComponent(eventUid)}/translate`, { method: "POST", body: { case_id: caseId } }))
}
export async function translateDerivedText(caseId: string, derivedId: string) {
  return TranslationSchema.parse(await fetchAPI(`/api/phones/media/derived/${encodeURIComponent(derivedId)}/translate`, { method: "POST", body: { case_id: caseId } }))
}
export interface ThreadTranslateCounts {
  in_conversation: number
  queued: number
  left_out: { no_text: number; already_translated: number; already_waiting: number }
}
export async function translateThread(caseId: string, threadKey: string) {
  return fetchAPI<ThreadTranslateCounts>("/api/phones/threads/translate", { method: "POST", body: { case_id: caseId, thread_key: threadKey } })
}
const TranslationsSchema = lazySchema(() => z.object({ items: z.record(z.string(), TranslationSchema) }))
export async function getTranslations(caseId: string, sourceType: "message" | "derived_text", keys: string[]) {
  return TranslationsSchema.parse(await fetchAPI("/api/phones/translations", { method: "POST", body: { case_id: caseId, source_type: sourceType, keys }, read: true })).items
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

/** One side of a communication edge: a person (dossier) or one phone identity (02 section 11.2). */
export type EdgeSubject = { identity_key: string } | { dossier_id: string }

export interface LinkEdgeCommunication {
  messages_ab: number; messages_ba: number; calls_ab: number; calls_ba: number; emails_ab: number; emails_ba: number
  first_instant: string | null; last_instant: string | null; phones: string[]; no_time_count: number | null
}

export interface LinkEdge {
  a: { label: string; identity_key?: string; dossier_id?: string }
  b: { label: string; identity_key?: string; dossier_id?: string }
  communication: LinkEdgeCommunication
  label: string
}

/** Combined edges between subjects, counted as Conversations counts Between A and B (direct, copies collapsed by
 * default), so an edge's count equals the list it opens. */
export async function getLinkEdges(caseId: string, subjects: EdgeSubject[], opts: { groupScope?: "direct" | "include_groups"; collapseCopies?: boolean } = {}) {
  return fetchAPI<{ edges: LinkEdge[]; financial_records?: boolean; money_absent?: string | null }>("/api/phones/link-analysis/edges", {
    method: "POST",
    body: { case_id: caseId, subjects, group_scope: opts.groupScope ?? "direct", collapse_copies: opts.collapseCopies ?? true },
    read: true,
  })
}

/** 07 section 8: whether the case holds financial evidence, and the sentence each money part shows when not. */
export interface FinancialPresence {
  has_financial_evidence: boolean
  source_documents: number | null
  ledger_rows: number
  phones: number | null
  phone_sentence: string | null
  financial_sentence: string | null
}
export async function getFinancialPresence(caseId: string) {
  return fetchAPI<FinancialPresence>(`/api/phones/financial-presence?case_id=${encodeURIComponent(caseId)}`)
}

export interface CrossingPerson { id: string; name: string }
export interface PaymentCrossingDay { offset: number; words: string; date: string; count: number; conversations_href: string }
/** XF-1: phone activity around a payment. */
export interface PaymentCrossing {
  transaction_id: string
  payment_date: string | null
  state: "linked" | "unlinked" | "no_counterparty" | "no_phones" | "no_date"
  sentence: string
  people?: CrossingPerson[]
  counterparty?: { kind: string; id: string; label: string | null }
  days: PaymentCrossingDay[]
  total?: number
  conversations_href?: string
  people_href?: string
  payee_dossier_offer?: boolean
}
export async function getPaymentCrossing(caseId: string, transactionId: string) {
  return fetchAPI<PaymentCrossing>(`/api/phones/crossings/payment/${encodeURIComponent(transactionId)}?case_id=${encodeURIComponent(caseId)}`)
}
export async function createPayeeDossier(caseId: string, transactionId: string) {
  return fetchAPI<{ id: string; display_name: string }>(
    `/api/phones/crossings/payment/${encodeURIComponent(transactionId)}/payee-dossier?case_id=${encodeURIComponent(caseId)}`,
    { method: "POST" },
  )
}
/** XF-2: a Graph person to its messages and calls on the phones. */
export interface PersonCrossing {
  state: "linked" | "unlinked"
  people: CrossingPerson[]
  total: number | null
  conversations_href?: string
  sentence: string
}
export async function getPersonCrossing(caseId: string, subject: { dossierId?: string; entityKey?: string }) {
  const q = new URLSearchParams({ case_id: caseId })
  if (subject.dossierId) q.set("dossier_id", subject.dossierId)
  if (subject.entityKey) q.set("entity_key", subject.entityKey)
  return fetchAPI<PersonCrossing>(`/api/phones/crossings/person?${q.toString()}`)
}
/** XF-8: payments suggested for a phone contact; never reviewed by this. */
export interface CounterpartySuggestions {
  identity_key: string
  label: string
  status: string
  state: "suggested" | "none" | "no_financial_records"
  sentence: string
  accounts: { account_id: string; identifier: string; identifier_kind: string; label: string | null }[]
  payment_total?: number
  payments?: { id: string; date: string | null; amount_minor: number; currency: string; direction: string; description: string | null; href: string }[]
  limitation?: string | null
}
export async function getCounterpartySuggestions(caseId: string, identityKey: string) {
  return fetchAPI<CounterpartySuggestions>(
    `/api/phones/crossings/counterparty-suggestions?case_id=${encodeURIComponent(caseId)}&identity_key=${encodeURIComponent(identityKey)}`,
  )
}
/** XF-4: what the phones did in a Timeline period. */
export interface PeriodCrossing {
  from: string
  to: string
  zone: string
  total: number
  sentence: string
  phones: { extraction_id: string; label: string; count: number; conversations_href: string; no_time?: number }[]
  lens_filter: StreamFilter & { lens_kinds: string[]; lane_by: string }
}
export async function getPeriodCrossing(caseId: string, from: string, to: string) {
  return fetchAPI<PeriodCrossing>(`/api/phones/crossings/period?case_id=${encodeURIComponent(caseId)}&from=${from}&to=${to}`)
}
