import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"

/** Loupe-wide search (03 section 11.4). */

const SnippetSchema = z.object({ before: z.string(), match: z.string(), after: z.string() })
export const HitSchema = z.object({
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
  open: z.object({ screen: z.string(), params: z.record(z.string(), z.unknown()) }),
})
export type SearchHit = z.infer<typeof HitSchema>
export const GroupSchema = z.object({
  group: z.string(),
  total: z.number(),
  items: z.array(HitSchema),
  next_cursor: z.string().nullable(),
  note: z.string().optional(),
  score: z.number().optional(),
})
export type SearchGroup = z.infer<typeof GroupSchema>
/** A phone still being read or only partly read: totals that count from it are not whole (03 3.8). */
const LimitSchema = z.object({ kind: z.string(), message: z.string() }).passthrough()
const GroupPageSchema = GroupSchema.extend({ complete: z.boolean().default(true), limits: z.array(LimitSchema).default([]) })

export const SearchSchema = z.object({
  query: z.string(),
  folded_query: z.string(),
  exact: z.boolean(),
  complete: z.boolean(),
  limits: z.array(LimitSchema).default([]),
  short: z.string().nullable(),
  groups: z.array(GroupSchema),
  not_searched: z.array(z.object({ group: z.string(), reason: z.string() })),
})
export type SearchResult = z.infer<typeof SearchSchema>

export async function searchCase(caseId: string, q: string, exact = false, signal?: AbortSignal): Promise<SearchResult> {
  const p = new URLSearchParams({ case_id: caseId, q, exact: String(exact) })
  return SearchSchema.parse(await fetchAPI(`/api/search?${p}`, { signal }))
}

export async function searchGroup(caseId: string, q: string, group: string, cursor: string | null, exact = false, signal?: AbortSignal) {
  const p = new URLSearchParams({ case_id: caseId, q, group, exact: String(exact), limit: "200" })
  if (cursor) p.set("cursor", cursor)
  return GroupPageSchema.parse(await fetchAPI(`/api/search/group?${p}`, { signal }))
}
