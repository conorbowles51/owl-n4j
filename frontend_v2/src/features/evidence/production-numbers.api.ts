import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { lazySchema } from "@/lib/lazy-schema"

/**
 * Production (Bates) numbers on evidence. Three kinds, always shown apart: Assigned (issued from this case's
 * numbered set), Received (entered, imported or confirmed by a person) and Suggested (read from a file name, a
 * suggestion until a person decides it).
 */
const Item = lazySchema(() =>
  z.object({
    id: z.string().optional(),
    kind: z.string(),
    text: z.string(),
    label: z.string().optional(),
    status: z.string().optional(),
    first_text: z.string().optional(),
    last_text: z.string().optional(),
    set_name: z.string().optional(),
    level: z.string().optional(),
    page_count: z.number().nullable().optional(),
    note: z.string().nullable().optional(),
    withdrawn: z.boolean().optional(),
  }).passthrough()
)
const Conflict = lazySchema(() => z.object({ kind: z.string(), words: z.string() }).passthrough())
const FileNumbers = lazySchema(() =>
  z.object({
    evidence_file_id: z.string(),
    assigned: z.array(Item),
    received: z.array(Item),
    suggested: z.array(Item),
    conflicts: z.array(Conflict),
  }).passthrough()
)
export type FileNumbersView = z.infer<typeof FileNumbers>
export type NumberItem = z.infer<typeof Item>
const SetView = lazySchema(() =>
  z.object({ id: z.string(), name: z.string(), prefix: z.string(), next_text: z.string() }).passthrough()
)
export type SetViewType = z.infer<typeof SetView>
const Overview = lazySchema(() =>
  z.object({ sets: z.array(SetView), files: z.record(z.string(), FileNumbers) }).passthrough()
)

const key = (caseId: string) => ["production-numbers", caseId]
const q = (caseId: string) => `case_id=${encodeURIComponent(caseId)}`

/** One request for the whole case; the Evidence list joins it to its rows, so no row costs a lookup. */
export function useProductionNumbers(caseId: string) {
  return useQuery({
    queryKey: key(caseId),
    enabled: !!caseId,
    staleTime: 30_000,
    queryFn: async () => Overview.parse(await fetchAPI(`/api/production-numbers?${q(caseId)}`, { read: true })),
  })
}

/** The line a list row prints: each standing number with its kind, so a suggestion never reads as a value. */
export function numbersLine(numbers: FileNumbersView | undefined): string | null {
  if (!numbers) return null
  const parts = [
    ...numbers.assigned.filter((n) => !n.withdrawn).map((n) => `${n.text} (assigned)`),
    ...numbers.received.filter((n) => n.status === "confirmed" && !n.withdrawn).map((n) => `${n.text} (received)`),
    ...numbers.suggested.map((n) => `${n.text} (suggested from the file name, not confirmed)`),
  ]
  return parts.length ? parts.join(" · ") : null
}

export function useProductionActions(caseId: string) {
  const client = useQueryClient()
  const done = () => client.invalidateQueries({ queryKey: key(caseId) })
  const post = (path: string, body: Record<string, unknown>) =>
    fetchAPI(`/api/production-numbers${path}`, { method: "POST", body: { case_id: caseId, ...body } })
  return {
    createSet: useMutation({
      mutationFn: (b: { name: string; prefix: string; start: number; padding: number }) => post("/sets", b),
      onSuccess: done,
    }),
    assign: useMutation({
      mutationFn: (b: { setId: string; fileId: string; level: "page" | "file" }) =>
        post(`/sets/${b.setId}/assign`, { file_ids: [b.fileId], level: b.level }),
      onSuccess: done,
    }),
    withdraw: useMutation({
      mutationFn: (b: { id: string; reason: string }) => post(`/assignments/${b.id}/withdraw`, { reason: b.reason }),
      onSuccess: done,
    }),
    enterReceived: useMutation({
      mutationFn: (b: { fileId: string; first: string; last?: string }) =>
        post("/received", { evidence_file_id: b.fileId, first: b.first, ...(b.last ? { last: b.last } : {}) }),
      onSuccess: done,
    }),
    decide: useMutation({
      mutationFn: (b: { fileId: string; first: string; last: string; confirm: boolean }) =>
        post("/suggestions/decide", {
          evidence_file_id: b.fileId, first_text: b.first, last_text: b.last, confirm: b.confirm,
        }),
      onSuccess: done,
    }),
    withdrawReceived: useMutation({
      mutationFn: (id: string) => post(`/received/${id}/withdraw`, {}),
      onSuccess: done,
    }),
  }
}
