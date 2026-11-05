import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { lazySchema } from "@/lib/lazy-schema"

/** Loupe-wide search (03 section 11.4). */

const SnippetSchema = lazySchema(() => z.object({ before: z.string(), match: z.string(), after: z.string() }))
export const HitSchema = lazySchema(() => z.object({
  kind: z.string(),
  title: z.string(),
  snippet: SnippetSchema.nullable(),
  phone_label: z.string().nullable().optional(),
  time: z.string().nullable().optional(),
  page: z.number().nullable().optional(),
  record_uid: z.string().nullable(),
  evidence_file_id: z.string().nullable(),
  identity_key: z.string().optional(),
  file_uid: z.string().optional(),
  machine_generated: z.boolean().optional(),
  label: z.string().optional(),
  /** Machine text's one origin mark (07 4.6): machine-generated and not yet confirmed, confirmed, or corrected. */
  origin: z.object({ state: z.string(), words: z.string().nullable(), confirmed: z.boolean() }).optional(),
  /** A machine translation (05 17.5): the language it was translated from, and the start of its original. */
  translated_from: z.string().nullable().optional(),
  original: z.object({ text: z.string(), clipped: z.boolean(), chars: z.number() }).optional(),
  /** A ledger row (the payments group): its citation, amount and parties as the ledger shows them now. */
  transaction_id: z.string().optional(),
  cite: z.string().optional(),
  date: z.string().nullable().optional(),
  amount_minor: z.string().optional(),
  currency: z.string().optional(),
  direction: z.string().optional(),
  from_name: z.string().nullable().optional(),
  to_name: z.string().nullable().optional(),
  account_label: z.string().nullable().optional(),
  included_in_totals: z.boolean().optional(),
  open: z.object({ screen: z.string(), params: z.record(z.string(), z.unknown()) }),
}))
export type SearchHit = z.infer<typeof HitSchema>
const PopulationSchema = lazySchema(() => z.object({
  credits_minor: z.string(),
  debits_minor: z.string(),
  credit_count: z.number(),
  debit_count: z.number(),
}))
export const PaymentTotalsSchema = lazySchema(() => z.object({
  currencies: z.array(z.object({ currency: z.string(), verified: PopulationSchema, p3: PopulationSchema })),
  counted_rows: z.number(),
  not_counted_rows: z.number(),
}))
export type PaymentTotals = z.infer<typeof PaymentTotalsSchema>
export const GroupSchema = lazySchema(() => z.object({
  group: z.string(),
  total: z.number(),
  items: z.array(HitSchema),
  next_cursor: z.string().nullable(),
  note: z.string().optional(),
  score: z.number().optional(),
  /** payments: money of every matching row per currency, verified (p0 to p2) and p3 stated apart, never added */
  totals: PaymentTotalsSchema.nullable().optional(),
  /** payments: what the group searches and what it does not */
  searched: z.string().optional(),
}))
export type SearchGroup = z.infer<typeof GroupSchema>
/** A phone still being read or only partly read: totals that count from it are not whole (03 3.8). */
const LimitSchema = lazySchema(() => z.object({ kind: z.string(), message: z.string() }).passthrough())
const GroupPageSchema = lazySchema(() => GroupSchema.extend({ complete: z.boolean().default(true), limits: z.array(LimitSchema).default([]) }))

export const SearchSchema = lazySchema(() => z.object({
  query: z.string(),
  folded_query: z.string(),
  exact: z.boolean(),
  complete: z.boolean(),
  limits: z.array(LimitSchema).default([]),
  short: z.string().nullable(),
  groups: z.array(GroupSchema),
  not_searched: z.array(z.object({ group: z.string(), reason: z.string() })),
}))
export type SearchResult = z.infer<typeof SearchSchema>

export async function searchCase(caseId: string, q: string, exact = false, signal?: AbortSignal): Promise<SearchResult> {
  const p = new URLSearchParams({ case_id: caseId, q, exact: String(exact) })
  return SearchSchema.parse(await fetchAPI(`/api/search?${p}`, { signal }))
}

export async function searchGroup(caseId: string, q: string, group: string, cursor: string | null, exact = false, signal?: AbortSignal, phones?: string[]) {
  const p = new URLSearchParams({ case_id: caseId, q, group, exact: String(exact), limit: "200" })
  if (cursor) p.set("cursor", cursor)
  if (phones?.length) p.set("phones", phones.join(","))
  return GroupPageSchema.parse(await fetchAPI(`/api/search/group?${p}`, { signal }))
}

/** A whole group kept as one phone selection for Add to… (07 J-5): its counts, and how many hits it could not hold. */
export async function freezeSearchGroup(caseId: string, q: string, group: string, exact: boolean, phones: string[]) {
  return fetchAPI<{ id: string; record_count: number; event_count: number; words: string; group_total: number; left_out: number }>("/api/search/group/selection", {
    method: "POST",
    body: { case_id: caseId, q, group, exact, phones },
  })
}

/** Saved keyword lists (03 section 11.2; 07 J-6, section 14): a search saved as named terms that runs on every phone
 * of the case, including phones added later. Totals per phone, term and group are the search's own totals. */
const RunPhoneSchema = lazySchema(() => z.object({
  extraction_id: z.string(),
  phone_label: z.string(),
  total: z.number(),
  terms: z.record(z.string(), z.record(z.string(), z.number())),
}))
export const KeywordListSchema = lazySchema(() => z.object({
  entry_id: z.string(),
  name: z.string(),
  terms: z.array(z.string()),
  exact: z.boolean(),
  created_by: z.string().nullable(),
  created_at: z.string().nullable(),
  last_run_at: z.string().nullable(),
  state: z.enum(["not_run", "current", "rerun_due", "failed"]),
  error: z.string().nullable(),
  theories: z.array(z.object({ id: z.string(), title: z.string().nullable() })),
  summary: z.string(),
  run: z
    .object({
      phones: z.array(RunPhoneSchema),
      terms: z.record(z.string(), z.number()),
      total: z.number(),
      ran_at: z.string(),
      groups: z.array(z.string()),
      group_words: z.record(z.string(), z.string()),
      not_counted: z.array(z.object({ extraction_id: z.string(), phone_label: z.string(), state: z.string().nullable(), message: z.string() })),
    })
    .nullable(),
}))
export type KeywordList = z.infer<typeof KeywordListSchema>
const KeywordListsSchema = lazySchema(() => z.object({ total: z.number(), items: z.array(KeywordListSchema) }))

export async function listKeywordLists(caseId: string, theory?: string): Promise<z.infer<typeof KeywordListsSchema>> {
  const p = new URLSearchParams({ case_id: caseId })
  if (theory) p.set("theory", theory)
  return KeywordListsSchema.parse(await fetchAPI(`/api/search/keyword-lists?${p}`))
}

export async function saveKeywordList(caseId: string, name: string, terms: string[], exact: boolean): Promise<KeywordList> {
  return KeywordListSchema.parse(
    await fetchAPI(`/api/search/keyword-lists`, { method: "POST", body: { case_id: caseId, name, terms, exact } }),
  )
}

export async function attachKeywordList(caseId: string, entryId: string, theoryId: string): Promise<KeywordList> {
  return KeywordListSchema.parse(
    await fetchAPI(`/api/search/keyword-lists/${encodeURIComponent(entryId)}/theories`, {
      method: "POST",
      body: { case_id: caseId, theory_id: theoryId },
    }),
  )
}

/** The terms typed in the save box: one per line, or separated by commas. */
export function splitTerms(typed: string): string[] {
  return typed
    .split(/[\n,]/)
    .map((t) => t.trim())
    .filter(Boolean)
}
