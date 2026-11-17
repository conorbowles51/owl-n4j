/**
 * Where phones were together (lx-phonetogether): the setting, the read and the pieces every overlay shares.
 * Backend: GET /api/cases/:id/relation-overlaps. The overlays are off until Neil approves the mock-up; a build sets
 * VITE_PHONE_TOGETHER=on, and a person can see them ahead of that with `?phone_together=on` (kept in this browser)
 * or `=off` to clear it. They need the phone layers (`phone_layers`) on as well.
 */
import { queryOptions } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"

/** The read takes at most this many phones; more phones on is stated, never cut without a word. */
export const MAX_TOGETHER_PHONES = 8

const Meeting = z.object({
  id: z.string(), phones: z.array(z.string()), start: z.string(), end: z.string(), cells: z.number(), readings: z.number(),
  days: z.array(z.string()),
  place: z.object({ lat: z.number(), lon: z.number(), square_m: z.number() }),
  precision: z.object({ best_accuracy_m: z.number().nullable(), accuracy_stated: z.boolean(), sources: z.array(z.string()), level: z.string() }),
  records: z.record(z.string(), z.array(z.string())), records_total: z.record(z.string(), z.number()),
  busy: z.object({ other_phones: z.number(), phones_total: z.number(), is_busy: z.boolean(), words: z.string() }).optional(),
})
const PhoneSide = z.object({ records: z.number(), first: z.string().nullable(), last: z.string().nullable(), record_ids: z.array(z.string()) })
const Contact = z.object({ id: z.string(), label: z.string(), basis: z.string(), phones: z.record(z.string(), PhoneSide), records: z.number(), first: z.string().nullable(), last: z.string().nullable() })
const Relay = z.object({ id: z.string(), first: z.string(), second: z.string(), via: z.string(), via_label: z.string(), first_at: z.string(), second_at: z.string(), gap_s: z.number(), records: z.array(z.string()) })

export const OverlapsSchema = z.object({
  case_id: z.string(), phones: z.array(z.object({ id: z.string(), label: z.string() })),
  together: z.array(Meeting), cells: z.number(), shared_contacts: z.array(Contact), relay_chains: z.array(Relay),
  pairs: z.array(z.object({ phones: z.array(z.string()), meetings: z.number(), days_together: z.number().nullable(), days_both_active: z.number().nullable() })),
  message: z.string(), contacts_message: z.string().nullable(), relay_message: z.string().nullable(),
  searched: z.array(z.string()), out_of_reach: z.array(z.string()),
})
export type Overlaps = z.infer<typeof OverlapsSchema>
export type Meeting = z.infer<typeof Meeting>

export function overlapsQuery(caseId: string, phones: string[], from?: string | null, to?: string | null) {
  const q = new URLSearchParams({ phones: phones.join(",") })
  if (from) q.set("from", from)
  if (to) q.set("to", to)
  return queryOptions({
    queryKey: ["relation-overlaps", caseId, phones.join(","), from ?? null, to ?? null],
    queryFn: async ({ signal }) => OverlapsSchema.parse(await fetchAPI(`/api/cases/${encodeURIComponent(caseId)}/relation-overlaps?${q}`, { read: true, signal })),
    enabled: !!caseId && phones.length >= 2 && phones.length <= MAX_TOGETHER_PHONES,
    staleTime: 60_000,
  })
}

/** "24 May 2024 00:30 to 02:45 UTC" (one day) or both ends in full. */
export function meetingWhen(m: Pick<Meeting, "start" | "end">): string {
  const f = (iso: string, withDay: boolean) => new Date(iso).toLocaleString("en-GB", { timeZone: "UTC", ...(withDay ? { day: "numeric", month: "short", year: "numeric" } : {}), hour: "2-digit", minute: "2-digit", hour12: false })
  const same = m.start.slice(0, 10) === m.end.slice(0, 10)
  return same ? `${f(m.start, true)} to ${new Date(m.end).toLocaleTimeString("en-GB", { timeZone: "UTC", hour: "2-digit", minute: "2-digit", hour12: false })} UTC` : `${f(m.start, true)} to ${f(m.end, true)} UTC`
}
