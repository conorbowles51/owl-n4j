import { z } from "zod"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { StaleSnapshotError, type StreamFilter } from "@/features/phones/api"
import { StreamIndexSchema, StreamWindowSchema, type StreamWindow } from "@/features/phones/schemas"
import type { StreamSource } from "@/features/phones/hooks/use-stream"
import { lazySchema } from "@/lib/lazy-schema"

/** The Case Timeline phone lens (03 section 9.3). */
export const LENS_KINDS = ["messages", "calls", "emails", "media", "locations", "web", "apps", "accounts", "device", "sensor", "other"] as const
export type LensKind = (typeof LENS_KINDS)[number]
export const DEFAULT_LENS_KINDS: LensKind[] = ["messages", "calls", "emails", "media", "locations"]
export type LaneBy = "phone" | "person" | "activity_class" | "kind"

export interface LensFilter extends StreamFilter {
  lens_kinds?: LensKind[]
  model_types?: string[]
  activity_classes?: string[]
  lane_by?: LaneBy
}

export const LensIndexSchema = lazySchema(() => StreamIndexSchema.extend({
  total: z.number(),
  lanes: z.array(z.object({ key: z.string(), label: z.string(), count: z.number() })),
  hidden: z.object({ count: z.number(), by_kind: z.record(z.string(), z.number()), words: z.string().nullable() }),
  kinds: z.array(z.object({ key: z.string(), label: z.string(), on: z.boolean() })),
  comm_filter_applies: z.boolean(),
  other_filter_applies: z.boolean(),
}))
export type LensIndex = z.infer<typeof LensIndexSchema>

export const BucketsSchema = lazySchema(() => z.object({
  case_id: z.string(),
  bucket: z.enum(["hour", "day", "week"]),
  zone: z.string(),
  lanes: z.array(z.object({ key: z.string(), label: z.string(), buckets: z.array(z.object({ start: z.string(), wall: z.string(), count: z.number(), no_data: z.boolean() })) })),
  no_data_words: z.string(),
  empty_words: z.string(),
}))
export type LensBuckets = z.infer<typeof BucketsSchema>

export const LensMoneySchema = lazySchema(() => z.object({
  label: z.string(),
  words: z.string(),
  proof_class: z.literal("p4"),
  run: z.object({ id: z.string(), finished_at: z.string().nullable() }).nullable(),
  buckets: z.array(z.object({ start: z.string(), wall: z.string(), end: z.string(), count: z.number() })),
  readings: z.number(),
  no_time: z.number(),
  rejected: z.number(),
  absent_words: z.string().nullable(),
}))
export type LensMoney = z.infer<typeof LensMoneySchema>

export const LensMoneyItemsSchema = lazySchema(() => z.object({
  total: z.number(),
  limit: z.number(),
  words: z.string(),
  items: z.array(z.object({
    result_id: z.string(), record_uid: z.string(), instant: z.string().nullable(), amount_text: z.string().nullable(), currency: z.string().nullable(),
    direction: z.string().nullable(), institution: z.string().nullable(), source: z.string().nullable(), phone_label: z.string().nullable(), outcome: z.string().nullable(),
    proof_class: z.literal("p4"), from_the_phone: z.literal(true),
  })),
}))
export type LensMoneyItems = z.infer<typeof LensMoneyItemsSchema>

async function stale<T>(p: Promise<T>): Promise<T> {
  try {
    return await p
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) throw new StaleSnapshotError()
    throw e
  }
}

export async function lensIndex(filter: LensFilter): Promise<LensIndex> {
  return LensIndexSchema.parse(await fetchAPI("/api/phones/timeline/index", { method: "POST", body: filter, read: true }))
}

export async function lensWindow(filter: LensFilter, snapshot: string, day: string | null, offset: number, limit: number): Promise<StreamWindow> {
  return StreamWindowSchema.parse(await stale(fetchAPI("/api/phones/timeline/window", { method: "POST", body: { filter, snapshot, day, offset, limit }, read: true })))
}

/** Show on Timeline (03 section 3.6): the day and offset of a record's entry in the lens, in window order. */
export async function lensLocateRecord(filter: LensFilter, snapshot: string, recordUid: string): Promise<{ day: string | null; offset: number; entry_uid: string }> {
  return fetchAPI("/api/phones/timeline/locate", { method: "POST", body: { filter, snapshot, record_uid: recordUid }, read: true })
}

export async function lensBuckets(filter: LensFilter, snapshot: string, start: string, end: string, bucket: "hour" | "day" | "week"): Promise<LensBuckets> {
  return BucketsSchema.parse(await stale(fetchAPI("/api/phones/timeline/buckets", { method: "POST", body: { filter, snapshot, start, end, bucket }, read: true })))
}

/** Phone money readings for the money lane (05 4.4): asked for apart, so they are in no total of the lens. */
export async function lensMoney(filter: LensFilter, start: string, end: string, bucket: "hour" | "day" | "week"): Promise<LensMoney> {
  return LensMoneySchema.parse(await fetchAPI("/api/phones/timeline/money", { method: "POST", body: { filter, start, end, bucket }, read: true }))
}

export async function lensMoneyItems(filter: LensFilter, start: string, end: string): Promise<LensMoneyItems> {
  return LensMoneyItemsSchema.parse(await fetchAPI("/api/phones/timeline/money", { method: "POST", body: { filter, start, end, items: true }, read: true }))
}

/** The lens as a source for the one phone list (useStream): the same list, copy and badges as Conversations. */
export const LENS_SOURCE: StreamSource = {
  index: (f) => lensIndex(f as LensFilter),
  window: (f, s, d, o, l) => lensWindow(f as LensFilter, s, d, o, l),
  locate: async () => {
    throw new Error("The lens keeps its scroll position instead of finding a row again.")
  },
}
