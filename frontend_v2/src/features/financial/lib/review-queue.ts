import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { randomRequestId } from "@/lib/browser-crypto"
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
  field: z
    .enum(["holder", "account_number", "period", "currency", "institution"])
    .nullish(),
  other_problems: z.number().default(0),
  problem_total: z.number().default(0),
  /** Every actionable blocker, the summary's first; `also` names the others in plain words. */
  reasons: z.array(z.string()).default([]),
  also: z.array(z.string()).default([]),
  /** True only when the proposed one-click fix leaves nothing else to fix. */
  fix_makes_ready: z.boolean().default(false),
  reader_file: z.boolean().optional(),
  copy_of: z.string().nullish(),
  set_aside: z.boolean().optional(),
  /** Proposed values for missing details (value, its source, whether it is certain). */
  proposals: z
    .record(
      z.string(),
      z.object({
        value: z.string(),
        label: z.string(),
        confirmed: z.boolean().default(false),
      })
    )
    .optional(),
})
export type QueueEntry = z.infer<typeof entry>

export const queueCounts = z.object({
  imported: z.number(),
  saving: z.number().default(0),
  waiting: z.number(),
  filled: z.number().default(0),
  reader_fix: z.number().default(0),
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

/** Statement files being read or prepared now, and files never read. */
export const readingProgress = z.object({
  files_total: z.number().default(0),
  files_done: z.number().default(0),
  files_reading: z.number().default(0),
  files_waiting_to_start: z.number().default(0),
  paused: z.boolean().default(false),
  unread_statement_files: z.number().default(0),
})
export type ReadingProgress = z.infer<typeof readingProgress>

export const reviewQueue = z.object({
  case_id: z.string(),
  file_ids: z.array(z.string()).default([]),
  counts: queueCounts,
  status_line: z.string(),
  reading: readingProgress.optional(),
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
  filled: z.array(entry).default([]),
  reader_fix: z.array(entry).default([]),
  reader_files: z
    .array(
      z.object({
        file_id: z.string(),
        filename: z.string(),
        batch_id: z.string().nullable(),
        statements: z.number(),
        file_statements: z.number().default(0),
        item_ids: z.array(z.string()),
        message: z.string(),
      })
    )
    .default([]),
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
  return useQuery<ReviewQueue>({
    queryKey: reviewQueueKey(caseId, fileIds),
    enabled,
    // The queue is a read of stored preparations; keep the last answer on
    // screen while a refresh runs, so Next never waits for it.
    placeholderData: keepPreviousData,
    // While statement files are being read, statements join the queue as
    // each file finishes.
    refetchInterval: (query): number | false =>
      isReading(query.state.data?.reading) ? READING_POLL_MS : false,
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

export const READING_POLL_MS = 15000

export function isReading(reading?: ReadingProgress) {
  return !!reading && (reading.files_reading > 0 || reading.files_waiting_to_start > 0)
}

/** "Reading 12 of 40 files…", or "" when nothing is being read. */
export function readingSentence(reading?: ReadingProgress) {
  if (!reading || !isReading(reading)) return ""
  const total = reading.files_total + reading.files_waiting_to_start
  if (reading.paused)
    return `Reading paused at ${reading.files_done} of ${total} files`
  return `Reading ${Math.min(reading.files_done + 1, total)} of ${total} files…`
}

/** Read the case's statement files that were never read or prepared. */
export async function readUnreadStatements(caseId: string) {
  const result = z
    .object({
      case_id: z.string(),
      added: z.number(),
      copies: z.number().default(0),
      batch_id: z.string().nullable(),
    })
    .parse(
      await fetchAPI(
        `/api/financial/statement-import/review/read-unread?case_id=${caseId}`,
        { method: "POST" }
      )
    )
  if (result.case_id !== caseId) throw Error("The answer belongs to another case.")
  return result
}

const status = z.object({
  case_id: z.string(),
  counts: queueCounts,
  status_line: z.string(),
  reading: readingProgress.optional(),
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

const heldEntry = z.object({
  item_id: z.string().nullable(),
  filename: z.string().default(""),
  period_start: z.string().default(""),
  period_end: z.string().default(""),
  reason: z.string(),
})
export type HeldStatement = z.infer<typeof heldEntry>
const saveResponse = z.object({
  request_id: z.string(),
  queued: z.number(),
  held: z.array(heldEntry),
  operations: z.array(
    z.object({ batch_id: z.string(), operation_id: z.string(), queued: z.number() })
  ),
})
const saveProgress = z.object({
  case_id: z.string(),
  found: z.number(),
  pending: z.number(),
  imported: z.number(),
  already_present: z.number(),
  duplicate_ignored: z.number(),
  failed: z.array(heldEntry),
  transaction_count: z.number(),
})

export type QueueSaveResult = {
  imported: number
  held: HeldStatement[]
  stillSaving: number
  message: string
}

/** "3 currency not printed: choose one, 1 already saved" — reasons, most common first. */
export function heldReasons(held: HeldStatement[]) {
  const counts = new Map<string, number>()
  for (const entry of held) counts.set(entry.reason, (counts.get(entry.reason) ?? 0) + 1)
  return [...counts]
    .sort((a, b) => b[1] - a[1])
    .map(([reason, n]) => `${n} ${reason.charAt(0).toLowerCase()}${reason.slice(1)}`)
    .join(", ")
}

export function saveResultLine(result: Omit<QueueSaveResult, "message">) {
  const parts = [`${result.imported} imported`]
  if (result.held.length)
    parts.push(`${result.held.length} held: ${heldReasons(result.held)}`)
  if (result.stillSaving)
    parts.push(
      `${result.stillSaving} still saving in the background (refresh the queue later)`
    )
  return parts.join(", ")
}

// About 2.5 s of admission per statement on the live case: ~25 s per request,
// so batch and evidence locks are held briefly and progress shows often.
const SAVE_CHUNK = 10
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Save ready statements from the queue, across batches. Each chunk is checked
 * on the server with the batch save's admission; accepted statements are
 * imported by the batch worker, which this waits for (bounded).
 */
export async function saveReadyStatements(
  caseId: string,
  itemIds: string[],
  {
    onProgress,
    pollMs = 3000,
    maxWaitMs = 10 * 60 * 1000,
  }: {
    onProgress?: (text: string) => void
    pollMs?: number
    maxWaitMs?: number
  } = {}
): Promise<QueueSaveResult> {
  const held: HeldStatement[] = []
  const operations: string[] = []
  for (let start = 0; start < itemIds.length; start += SAVE_CHUNK) {
    onProgress?.(
      `Checking statements ${start + 1}–${Math.min(start + SAVE_CHUNK, itemIds.length)} of ${itemIds.length}…`
    )
    const response = saveResponse.parse(
      await fetchAPI(
        `/api/financial/statement-import/review/save?case_id=${caseId}`,
        {
          method: "POST",
          body: {
            item_ids: itemIds.slice(start, start + SAVE_CHUNK),
            request_id: randomRequestId(),
          },
          timeout: 300000,
        }
      )
    )
    held.push(...response.held)
    operations.push(...response.operations.map((op) => op.operation_id))
  }
  let progress: z.infer<typeof saveProgress> | null = null
  const started = Date.now()
  while (operations.length) {
    const search = new URLSearchParams({ case_id: caseId })
    for (const id of operations) search.append("operation_id", id)
    progress = saveProgress.parse(
      await fetchAPI(`/api/financial/statement-import/review/save-result?${search}`)
    )
    if (!progress.pending || Date.now() - started > maxWaitMs) break
    onProgress?.(
      `Saving: ${progress.imported + progress.already_present} imported, ${progress.pending} still saving…`
    )
    await sleep(pollMs)
  }
  const result = {
    imported: (progress?.imported ?? 0) + (progress?.already_present ?? 0),
    held: [
      ...held,
      ...(progress?.failed ?? []),
      ...Array.from({ length: progress?.duplicate_ignored ?? 0 }, () => ({
        item_id: null,
        filename: "",
        period_start: "",
        period_end: "",
        reason: "Set aside as a copy of another statement",
      })),
    ],
    stillSaving: progress?.pending ?? 0,
  }
  return { ...result, message: saveResultLine(result) }
}

const fillResponse = z.object({
  case_id: z.string(),
  filled: z.number(),
  statements: z.number(),
  failed: z.number(),
  ready_item_ids: z.array(z.string()),
})

const hasConfirmed = (entry: QueueEntry) =>
  Object.values(entry.proposals ?? {}).some((proposal) => proposal.confirmed)

/**
 * The queue's save: first the details the system filled with certainty
 * (confirmed proposals, saved as System), then every ready statement, each
 * checked again with the batch save's admission.
 */
export async function fillAndSaveReady(
  caseId: string,
  data: ReviewQueue,
  options: Parameters<typeof saveReadyStatements>[2] = {}
): Promise<QueueSaveResult & { filled: number }> {
  let filled = 0
  const ids = data.ready.map((entry) => entry.id)
  if (data.filled.length || data.items.some(hasConfirmed)) {
    options.onProgress?.("Filling the details found automatically…")
    const response = fillResponse.parse(
      await fetchAPI(`/api/financial/statement-import/review/fill?case_id=${caseId}`, {
        method: "POST",
        body: { file_ids: data.file_ids },
        timeout: 300000,
      })
    )
    filled = response.filled
    ids.push(...response.ready_item_ids.filter((id) => !ids.includes(id)))
  }
  if (!ids.length) {
    const line = filled
      ? `${filled} ${filled === 1 ? "statement's details" : "statements' details"} filled automatically; none is ready to save yet`
      : "Nothing is ready to save"
    return { imported: 0, held: [], stillSaving: 0, message: line, filled }
  }
  const result = await saveReadyStatements(caseId, ids, options)
  return {
    ...result,
    filled,
    message: filled
      ? `${result.message} (details filled automatically on ${filled} as System; change any in its statement)`
      : result.message,
  }
}
