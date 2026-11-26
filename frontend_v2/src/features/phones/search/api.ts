import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { lazySchema } from "@/lib/lazy-schema"
import { HitSchema } from "@/features/search/api"
import { StreamRowSchema } from "../schemas"

/** Search every phone (Phones screen 2): counts by kind and phone, grouped hits, people saved differently, next steps. */

/** A hit's day in the zone the screen shows times in, with its first and last instant (UTC). */
const DaySchema = z.object({ date: z.string(), from: z.string(), to: z.string(), zone: z.string() })
export type HitDay = z.infer<typeof DaySchema>

const PhoneHitSchema = lazySchema(() => HitSchema.and(z.object({
  extraction_id: z.string().optional(),
  event_uid: z.string().optional(),
  thread_key: z.string().nullable().optional(),
  thread_title: z.string().nullable().optional(),
  where: z.string().optional(),
  deleted: z.boolean().optional(),
  masked: z.boolean().optional(),
  field_path: z.string().optional(),
  value_index: z.number().optional(),
  folder: z.string().nullable().optional(),
  direction: z.string().optional(),
  instant: z.string().nullable().optional(),
  day: DaySchema.nullable().optional(),
})))
export type PhoneHit = z.infer<typeof PhoneHitSchema>

const KindSchema = lazySchema(() => z.object({
  kind: z.string(), label: z.string(), total: z.number(), by_phone: z.record(z.string(), z.number()), deleted: z.number(),
}))
export type KindCount = z.infer<typeof KindSchema>

const StepSchema = lazySchema(() => z.object({
  id: z.string(), rank: z.number().optional(), title: z.string(), why: z.string(),
  open: z.object({ screen: z.string(), params: z.record(z.string(), z.string().nullable()) }),
}))
export type NextStep = z.infer<typeof StepSchema>

const SavedSchema = lazySchema(() => z.object({
  identity_keys: z.array(z.string()), person_id: z.string().nullable(), name: z.string(), sentence: z.string(),
  names: z.array(z.object({ extraction_id: z.string(), phone: z.string(), names: z.array(z.string()) })),
  own_phones: z.array(z.object({ extraction_id: z.string(), phone: z.string() })),
}))
export type SavedDifferently = z.infer<typeof SavedSchema>

const LimitSchema = lazySchema(() => z.object({ message: z.string() }).passthrough())

export const PhoneSearchSchema = lazySchema(() => z.object({
  query: z.string(),
  exact: z.boolean(),
  short: z.string().nullable(),
  number_digits: z.string().nullable(),
  phones: z.array(z.object({ extraction_id: z.string(), label: z.string() })),
  total: z.number(),
  kinds: z.array(KindSchema),
  groups: z.array(z.object({ kind: z.string(), label: z.string(), total: z.number(), items: z.array(PhoneHitSchema), next_cursor: z.string().nullable() })),
  saved_differently: z.array(SavedSchema),
  complete: z.boolean(),
  limits: z.array(LimitSchema),
  next_steps: z.array(StepSchema),
  /** the people saved differently, and their steps, come from searchPhonesPeople, asked beside */
  people_pending: z.boolean().optional(),
  not_searched: z.array(z.object({ group: z.string(), reason: z.string() })),
}))
export type PhoneSearchResult = z.infer<typeof PhoneSearchSchema>

export interface PhoneSearchParams {
  q: string
  exact?: boolean
  phones?: string[]
  from?: string | null
  to?: string | null
}

function query(caseId: string, p: PhoneSearchParams, more: Record<string, string> = {}) {
  const s = new URLSearchParams({ case_id: caseId, q: p.q, ...more })
  if (p.exact) s.set("exact", "true")
  if (p.phones?.length) s.set("phones", p.phones.join(","))
  if (p.from) s.set("from", p.from)
  if (p.to) s.set("to", p.to)
  return s
}

export async function searchPhones(caseId: string, p: PhoneSearchParams, signal?: AbortSignal): Promise<PhoneSearchResult> {
  // the people saved differently fold the case's names; they come beside the first results (searchPhonesPeople)
  return PhoneSearchSchema.parse(await fetchAPI(`/api/search/phones?${query(caseId, p, { people: "false" })}`, { signal }))
}

const PeopleSchema = lazySchema(() => z.object({ saved_differently: z.array(SavedSchema), steps: z.array(StepSchema) }))

export async function searchPhonesPeople(caseId: string, p: PhoneSearchParams, signal?: AbortSignal) {
  return PeopleSchema.parse(await fetchAPI(`/api/search/phones/people?${query(caseId, { q: p.q, exact: p.exact, phones: p.phones })}`, { signal }))
}

const KindPageSchema = lazySchema(() => z.object({
  kind: z.string(), label: z.string(), total: z.number(), items: z.array(PhoneHitSchema), next_cursor: z.string().nullable(),
  complete: z.boolean(),
}))

export async function searchPhonesKind(caseId: string, p: PhoneSearchParams, kind: string, cursor: string | null, signal?: AbortSignal) {
  const more: Record<string, string> = { kind, limit: "200" }
  if (cursor) more.cursor = cursor
  return KindPageSchema.parse(await fetchAPI(`/api/search/phones/kind?${query(caseId, p, more)}`, { signal }))
}

const ElsewhereSchema = lazySchema(() => z.object({ counts: z.record(z.string(), z.number()), step: StepSchema.nullable() }))

export async function searchPhonesElsewhere(caseId: string, q: string, exact: boolean, signal?: AbortSignal) {
  return ElsewhereSchema.parse(await fetchAPI(`/api/search/phones/elsewhere?${query(caseId, { q, exact })}`, { signal }))
}

export const HitContextSchema = lazySchema(() => z.object({
  event_uid: z.string(), extraction_id: z.string(), phone: z.string(), thread_key: z.string().nullable(),
  thread_title: z.string().nullable(), thread_count: z.number().nullable(), deleted: z.boolean(),
  items: z.array(StreamRowSchema), note: z.string().nullable(), day: DaySchema.nullable().optional(),
}))
export type HitContext = z.infer<typeof HitContextSchema>

export async function hitContext(caseId: string, eventUid: string, signal?: AbortSignal): Promise<HitContext> {
  const s = new URLSearchParams({ case_id: caseId, event_uid: eventUid })
  return HitContextSchema.parse(await fetchAPI(`/api/search/phones/context?${s}`, { signal }))
}
