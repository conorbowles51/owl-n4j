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
