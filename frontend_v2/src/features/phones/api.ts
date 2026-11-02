import { ApiError, fetchAPI } from "@/lib/api-client"
import {
  PhonesSchema,
  RecordDetailSchema,
  StreamIndexSchema,
  StreamWindowSchema,
  type RecordDetail,
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
