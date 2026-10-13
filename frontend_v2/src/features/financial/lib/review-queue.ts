import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import type { StatementImportReceipt } from "../components/StatementImportPanel"

const entry = z.object({
  id: z.string(),
  batch_id: z.string().nullable(),
  file_id: z.string(),
  source_id: z.string(),
  statement_id: z.string().nullish(),
  filename: z.string(),
  holder: z.string().default(""),
  account: z.string().default(""),
  institution: z.string().default(""),
  currency: z.string().default(""),
  period_start: z.string().default(""),
  period_end: z.string().default(""),
  page: z.number().nullish(),
  can_import: z.boolean().default(false),
  status: z.string(),
  bucket: z.string(),
  file_ids: z.array(z.string()).default([]),
  file_position: z.number().default(1),
  file_statements: z.number().default(1),
  issue: z.string().optional(),
  issue_reason: z.string().optional(),
  row_id: z.string().nullish(),
  field: z.enum(["holder", "account_number", "period"]).nullish(),
  other_problems: z.number().default(0),
  problem_total: z.number().default(0),
  copy_of: z.string().nullish(),
  set_aside: z.boolean().optional(),
})
export type QueueEntry = z.infer<typeof entry>

export const queueCounts = z.object({
  imported: z.number(),
  saving: z.number().default(0),
  waiting: z.number(),
  ready: z.number(),
  copies: z.number(),
  unreadable: z.number(),
  unreadable_files: z.number().default(0),
  rechecking: z.number().default(0),
  left_unimported: z.number().default(0),
  assigned: z.number().default(0),
  unexplained: z.number().default(0),
})
export type QueueCounts = z.infer<typeof queueCounts>

export const reviewQueue = z.object({
  case_id: z.string(),
  file_ids: z.array(z.string()).default([]),
  counts: queueCounts,
  status_line: z.string(),
  items: z.array(entry),
  copies: z.array(entry).default([]),
  unreadable: z.array(entry).default([]),
  unreadable_files: z
    .array(
      z.object({
        batch_id: z.string(),
        source_id: z.string().nullish(),
        file_id: z.string().nullish(),
        filename: z.string(),
        message: z.string(),
      })
    )
    .default([]),
  rechecking: z.array(entry).default([]),
  ready: z.array(entry).default([]),
  ready_batches: z
    .array(z.object({ batch_id: z.string(), statements: z.number() }))
    .default([]),
  elapsed_ms: z.number().optional(),
})
export type ReviewQueue = z.infer<typeof reviewQueue>

export const reviewQueueKey = (caseId: string, fileIds: string[] = []) => [
  "financial-review-queue",
  caseId,
  [...fileIds].sort().join(","),
]

export function useReviewQueue(
  caseId: string,
  fileIds: string[] = [],
  enabled = true
) {
  return useQuery({
    queryKey: reviewQueueKey(caseId, fileIds),
    enabled,
    // The queue is a read of stored preparations; keep the last answer on
    // screen while a refresh runs, so Next never waits for it.
    placeholderData: keepPreviousData,
    queryFn: async ({ signal }) => {
      const search = new URLSearchParams({ case_id: caseId })
      for (const id of fileIds) search.append("file_id", id)
      const result = reviewQueue.parse(
        await fetchAPI(
          `/api/financial/statement-import/review/queue?${search}`,
          { signal, timeout: 60000 }
        )
      )
      if (result.case_id !== caseId)
        throw Error("The review queue belongs to another case.")
      return result
    },
  })
}

const status = z.object({
  case_id: z.string(),
  counts: queueCounts,
  status_line: z.string(),
})

export function useReviewStatus(caseId: string, enabled = true) {
  return useQuery({
    queryKey: ["financial-review-status", caseId],
    enabled,
    queryFn: async ({ signal }) => {
      const result = status.parse(
        await fetchAPI(
          `/api/financial/statement-import/review/status?case_id=${caseId}`,
          { signal, timeout: 60000 }
        )
      )
      if (result.case_id !== caseId)
        throw Error("The status belongs to another case.")
      return result
    },
  })
}

export function useReviewCases(enabled = true) {
  return useQuery({
    queryKey: ["financial-review-cases"],
    enabled,
    queryFn: async () =>
      z
        .object({
          cases: z.array(
            z.object({
              case_id: z.string(),
              title: z.string(),
              last_batch_activity: z.string().nullish(),
            })
          ),
        })
        .parse(await fetchAPI("/api/financial/statement-import/review/cases"))
        .cases,
  })
}

/** Per evidence file: the queue's own counts, so file lists never count work differently. */
export type QueueFileWork = { waiting: number; unreadable: number; ready: number }

export function queueFileWork(data: ReviewQueue | undefined) {
  const byFile = new Map<string, QueueFileWork>()
  if (!data) return byFile
  const add = (ids: (string | null | undefined)[], key: keyof QueueFileWork) => {
    for (const id of new Set(ids.filter(Boolean) as string[])) {
      const work = byFile.get(id) ?? { waiting: 0, unreadable: 0, ready: 0 }
      work[key] += 1
      byFile.set(id, work)
    }
  }
  for (const entry of data.items) add(entry.file_ids, "waiting")
  for (const entry of data.unreadable) add(entry.file_ids, "unreadable")
  for (const file of data.unreadable_files) add([file.file_id, file.source_id], "unreadable")
  for (const entry of data.ready) add(entry.file_ids, "ready")
  return byFile
}

/** The queue route for some files (all of a batch's files, or one file), optionally at one entry. */
export function queueHref(caseId: string, fileIds: string[] = [], itemId?: string) {
  const search = new URLSearchParams({ view: "statements", queue: "1" })
  const ids = [...new Set(fileIds)].filter(Boolean)
  if (ids.length) search.set("queueFiles", ids.join(","))
  if (itemId) search.set("queueItem", itemId)
  return `/cases/${caseId}/financial?${search}`
}

const plural = (n: number, one: string, many: string) =>
  `${n} ${n === 1 ? one : many}`

/** What a save from the queue did, in one plain sentence. */
export function importOutcome(receipt?: StatementImportReceipt) {
  const payments = receipt?.transaction_count ?? 0
  const held = receipt?.incomplete_count ?? 0
  if (held > 0)
    return {
      held: true,
      message: `Saved but held: ${plural(held, "record is", "records are")} missing a value and ${held === 1 ? "stays" : "stay"} outside totals${payments ? ` (${plural(payments, "payment", "payments")} are in the ledger)` : ""}. One more step: complete ${held === 1 ? "it" : "them"} under Records held outside totals in Transactions.`,
    }
  if (!payments)
    return {
      held: false,
      message:
        "Imported: the statement's account, dates and balances are saved. It has no payments.",
    }
  return {
    held: false,
    message: `Imported: now in the ledger (${plural(payments, "payment", "payments")}).`,
  }
}

export function entryPeriod(entry: QueueEntry) {
  if (!entry.period_start && !entry.period_end) return "dates not read"
  return `${entry.period_start || "?"} to ${entry.period_end || "?"}`
}
