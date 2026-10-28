import { useRef } from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { randomRequestId } from "@/lib/browser-crypto"
import { formatLedgerAmount } from "./ledger-format"
import { filledBySave, listWords, missingRequired } from "./statement-needs"
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
  /** Nothing was read from pages that carry text: a reader problem, reported; `held_bucket` is the list it had its actions in. */
  reader_gap: z.boolean().optional(),
  reader_gap_line: z.string().optional(),
  held_bucket: z.string().optional(),
  copy_of: z.string().nullish(),
  set_aside: z.boolean().optional(),
  /** "same_file_read": this upload's reading failed; the same bytes were read through another upload.
   * "same_pages_read": the same, for a file with other bytes whose every page is identical. */
  copy_reason: z.string().nullish(),
  /** A fund statement (holdings, no payments) set aside as not a payment statement, with the reason. */
  not_payment: z.object({ kind: z.string().nullish(), label: z.string().nullish(), reason: z.string().nullish() }).nullish(),
  /** Printed opening and closing balances as read (minor units; null when not read), for checking against the PDF. */
  opening_minor: z.string().nullish(),
  closing_minor: z.string().nullish(),
  balance_status: z.string().optional(),
  transaction_count: z.number().nullish(),
  /** Every page the listed issue is on, and what the checks said about it (for plain instructions). */
  issue_pages: z.array(z.number()).default([]),
  issue_messages: z.array(z.string()).default([]),
  /** Why Loupe could not settle it alone, in plain sentences (what the pages print, what the account holds). */
  why: z.array(z.string()).default([]),
  /** The latest outcome of reading its page images, in plain words (why it did not settle it, or why it was not read). */
  vision_reading: z
    .object({
      status: z.string().nullish(),
      reason: z.string().nullish(),
      message: z.string().default(""),
      line: z.string().default(""),
      /** Rule 2: a reading that checks out, beside the person's saved work (values as compared). */
      offer: z
        .object({ mine: z.record(z.string(), z.unknown()), offered: z.record(z.string(), z.unknown()) })
        .nullish(),
    })
    .nullish(),
  /** Who saved the held work (their own corrections or added rows), when that is what is held. */
  worked_by: z.object({ user_id: z.string(), name: z.string() }).nullish(),
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
  /** Failed files that are not reading problems: removed from Financial or no longer in the case. */
  removed_files: z.number().default(0),
  /** Failed files set aside as copies; already included in `copies`. */
  copy_files: z.number().default(0),
  rechecking: z.number().default(0),
  left_unimported: z.number().default(0),
  assigned: z.number().default(0),
  unexplained: z.number().default(0),
  /** Fund statements set aside as not payment statements. */
  not_payment: z.number().default(0),
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
  not_payment: z.array(entry).default([]),
  unreadable: z.array(entry).default([]),
  unreadable_files: z
    .array(
      z.object({
        batch_id: z.string(),
        source_id: z.string().nullish(),
        file_id: z.string().nullish(),
        filename: z.string(),
        message: z.string(),
        /** Set when the retained PDF can be read afresh by an explicit request (its restart copy is gone). */
        read_afresh_revision: z.string().nullish(),
      })
    )
    .default([]),
  /** Files that could not be prepared, set aside because the same file (or the same pages) was read through another upload. */
  copy_files: z
    .array(
      z.object({
        batch_id: z.string(),
        source_id: z.string().nullish(),
        file_id: z.string().nullish(),
        filename: z.string(),
        message: z.string(),
        copy_of: z.string().nullish(),
        copy_reason: z.string().nullish(),
      })
    )
    .default([]),
  set_aside_files: z
    .array(
      z.object({
        batch_id: z.string(),
        source_id: z.string().nullish(),
        file_id: z.string().nullish(),
        filename: z.string(),
        message: z.string(),
        reason: z.enum(["removed", "gone", "copy"]),
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
  /** Paged reads (limit given): full list lengths, this page, issue counts over every waiting entry. */
  totals: z.record(z.string(), z.number()).optional(),
  page: z
    .object({
      list: z.string(),
      issue: z.string().nullish(),
      offset: z.number(),
      limit: z.number().nullish(),
      returned: z.number(),
      total: z.number(),
    })
    .optional(),
  issue_counts: z.record(z.string(), z.number()).optional(),
  /** One account's same proposed value on several waiting statements: one confirmation saves them all. */
  proposal_groups: z
    .array(
      z.object({
        id: z.string(),
        field: z.string(),
        value: z.string(),
        basis: z.string(),
        label: z.string(),
        account: z.string(),
        institution: z.string(),
        statements: z.number(),
        entry_ids: z.array(z.string()),
      })
    )
    .optional(),
  /** Every ready entry's id, never truncated by paging. */
  ready_item_ids: z.array(z.string()).optional(),
  /** True: this answer predates the latest change; a current one is being built. */
  refreshing: z.boolean().optional(),
  as_of: z.string().nullish(),
})
export type ReviewQueue = z.infer<typeof reviewQueue>

/** The server's list names for paging (`page_list`). */
export type QueuePageList = "waiting" | "ready" | "filled" | "reader_fix" | "rechecking" | "copies" | "unreadable" | "not_payment"
export const QUEUE_PAGE_SIZE = 50
/** Shared fixes act on every statement of one issue: one capped read of them all. */
export const QUEUE_BULK_LIMIT = 5000

/** Reads the whole queue (every list complete), waiting for a current build. */
export async function fetchReviewQueue(caseId: string, fileIds: string[] = [], signal?: AbortSignal) {
  const search = new URLSearchParams({ case_id: caseId })
  for (const id of fileIds) search.append("file_id", id)
  const result = reviewQueue.parse(
    await fetchAPI(`/api/financial/statement-import/review/queue?${search}`, { signal, timeout: 60000 })
  )
  if (result.case_id !== caseId) throw Error("The review queue belongs to another case.")
  return result
}

/**
 * One page of one queue list (counts and status line stay whole-case). A
 * paged read may be answered at once from a queue built moments ago
 * (`refreshing`); `fresh()` makes the next read wait for a current one, for
 * the refetch right after a save or fix. Against a server without paging
 * the full lists come back and the caller pages them on screen.
 */
export function useReviewQueuePage(
  caseId: string,
  fileIds: string[],
  page: { list: QueuePageList; issue?: string; offset?: number; limit?: number },
  enabled = true
) {
  const wantFresh = useRef(false)
  const limit = page.limit ?? QUEUE_PAGE_SIZE
  const offset = page.offset ?? 0
  const query = useQuery<ReviewQueue>({
    queryKey: [...reviewQueueKey(caseId, fileIds), "page", page.list, page.issue || "", offset, limit],
    enabled,
    placeholderData: keepPreviousData,
    refetchInterval: (current): number | false =>
      isReading(current.state.data?.reading) || isMoving(current.state.data?.counts) || current.state.data?.refreshing
        ? READING_POLL_MS
        : false,
    queryFn: async ({ signal }) => {
      const search = new URLSearchParams({ case_id: caseId })
      for (const id of fileIds) search.append("file_id", id)
      search.set("limit", String(limit))
      search.set("offset", String(offset))
      search.set("page_list", page.list)
      if (page.issue) search.set("issue", page.issue)
      if (wantFresh.current) search.set("fresh", "1")
      wantFresh.current = false
      const result = reviewQueue.parse(
        await fetchAPI(`/api/financial/statement-import/review/queue?${search}`, { signal, timeout: 60000 })
      )
      if (result.case_id !== caseId) throw Error("The review queue belongs to another case.")
      return result
    },
  })
  return Object.assign(query, {
    /** Refetch, waiting for a queue built from the current data. */
    refetchFresh: () => {
      wantFresh.current = true
      return query.refetch()
    },
  })
}

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
    // each file finishes; while statements are being checked again or saved,
    // they move on by themselves. No refresh button is needed for either.
    refetchInterval: (query): number | false =>
      isReading(query.state.data?.reading) || isMoving(query.state.data?.counts)
        ? READING_POLL_MS
        : false,
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

/** Statements the server is still checking again or saving. */
export function isMoving(counts?: { rechecking?: number; saving?: number }) {
  return Boolean(counts && ((counts.rechecking ?? 0) > 0 || (counts.saving ?? 0) > 0))
}

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

/**
 * Where a statement stands after a save, from the refreshed queue: what the
 * save filled, and when it still waits, exactly what is still needed and why.
 */
export function savedOutcome(data: ReviewQueue, entry: QueueEntry) {
  const same = (candidate: QueueEntry) => candidate.id === entry.id
  const waiting = data.items.find(same)
  const after = waiting ?? [...data.ready, ...data.filled, ...data.unreadable].find(same)
  const filled = after ? filledBySave(entry, after) : []
  const saved = filled.length ? `Saved your ${listWords(filled.map((need) => need.label))}.` : "Saved."
  if (waiting) {
    const missing = missingRequired(waiting)
    const why = waiting.issue ? ` Why it is held: ${waiting.issue.replace(/\.?$/, ".")}` : ""
    return {
      held: true,
      message: missing.length
        ? `${saved} Still needed before it can be imported: ${listWords(missing.map((need) => need.label))}.${why}`
        : `${saved} Still needed before it can be imported: ${waiting.issue || "a check"}.`,
    }
  }
  if (data.ready.some(same) || data.filled.some(same))
    return { held: false, message: `${saved} Ready to import: use Import at the top of the queue.` }
  if (data.unreadable.some(same))
    return { held: true, message: `${saved} Nothing could be read from it yet: open it to check its pages.` }
  return { held: false, message: `${saved} Nothing more is needed from you here.` }
}

/** "opening 1,000.00 USD · closing 950.50 USD · 12 payments read": as printed, never a guessed zero. */
export function entryBalances(entry: QueueEntry) {
  const money = (minor: string | null | undefined) => {
    if (minor === null || minor === undefined || minor === "") return "not read"
    if (!entry.currency) return `${formatLedgerAmount(minor, "").text} (minor units; currency not chosen)`
    const amount = formatLedgerAmount(minor, entry.currency)
    return amount.scaled ? `${amount.text} ${amount.currency}` : `${amount.text} minor units ${amount.currency}`
  }
  const parts = [`opening ${money(entry.opening_minor)}`, `closing ${money(entry.closing_minor)}`]
  if (typeof entry.transaction_count === "number")
    parts.push(`${entry.transaction_count} ${entry.transaction_count === 1 ? "payment" : "payments"} read`)
  if (entry.balance_status === "matches") parts.push("balances add up")
  else if (entry.balance_status === "difference") parts.push("balances do not add up")
  return parts.join(" · ")
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
  /** Statements sent to be saved; every one is imported, held or still importing. */
  sent?: number
  /** Counted as ready before the save but never sent: their details were filled and they still are not ready. */
  notReady?: QueueEntry[]
  /** How many the queue counted as ready (ready + details to fill) when Import was pressed. */
  counted?: number
  /** Waiting statements that filling their confirmed details made ready, sent as well. */
  madeReady?: number
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

/**
 * What the save did, from the server's answers only: imported, held with
 * reasons, still importing, and (when known) the ones counted as ready that
 * were never sent. Statements the server has not reported on are counted
 * too, so the parts always add up to the number counted.
 */
export function saveResultLine(result: Omit<QueueSaveResult, "message">) {
  const parts = [`${result.imported} imported`]
  if (result.held.length)
    parts.push(`${result.held.length} held: ${heldReasons(result.held)}`)
  if (result.stillSaving)
    parts.push(
      `${result.stillSaving} still importing in the background (refresh the queue later)`
    )
  const notReady = result.notReady?.length ?? 0
  if (notReady)
    parts.push(
      `${notReady} not imported: details filled, but ${notReady === 1 ? "it still needs" : "they still need"} something (listed under Waiting for you)`
    )
  if (result.sent !== undefined) {
    const unreported = result.sent - result.imported - result.held.length - result.stillSaving
    if (unreported > 0)
      parts.push(`${unreported} not reported yet (refresh the queue to see where ${unreported === 1 ? "it stands" : "they stand"})`)
  }
  const line = parts.join(", ")
  const total = (result.counted ?? 0) + (result.madeReady ?? 0)
  if (result.counted === undefined || total === result.imported) return line
  return `Of ${result.counted} counted as ready${result.madeReady ? ` (and ${result.madeReady} made ready by filling details)` : ""}: ${line}`
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
      `Importing: ${progress.imported + progress.already_present} imported, ${progress.pending} still importing…`
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
    sent: itemIds.length,
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
  const ids = data.ready_item_ids ? [...data.ready_item_ids] : data.ready.map((entry) => entry.id)
  const counted = ids.length + data.filled.length
  // Filled statements are sent only if filling made them ready.
  let notReady: QueueEntry[] = []
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
    const sent = new Set(ids)
    notReady = data.filled.filter((entry) => !sent.has(entry.id))
  }
  const listedReady = new Set([
    ...(data.ready_item_ids ?? []),
    ...[...data.ready, ...data.filled].map((entry) => entry.id),
  ])
  const madeReady = ids.filter((id) => !listedReady.has(id)).length
  if (!ids.length) {
    const result = { imported: 0, held: [], stillSaving: 0, sent: 0, notReady, counted, madeReady }
    const line = counted
      ? saveResultLine(result)
      : filled
        ? `${filled} ${filled === 1 ? "statement's details" : "statements' details"} filled automatically; none is ready to save yet`
        : "Nothing is ready to save"
    return { ...result, message: line, filled }
  }
  const saved = await saveReadyStatements(caseId, ids, options)
  const result = { ...saved, notReady, counted, madeReady }
  const line = saveResultLine(result)
  return {
    ...result,
    filled,
    message: filled
      ? `${line} (details filled automatically on ${filled} as System; change any in its statement)`
      : line,
  }
}

const readAfreshResponse = z.object({
  requested: z.number(),
  queued: z.number(),
  already: z.number(),
  refused: z.array(z.object({ batch_id: z.string(), source_id: z.string(), message: z.string() })),
})

/**
 * Explicitly reads the queue's retained PDFs afresh whose restart copy is gone.
 * Each file is checked and byte-verified on the server exactly as a single request.
 */
export async function readRetainedAfresh(caseId: string, data: ReviewQueue): Promise<string> {
  const files = data.unreadable_files
    .filter((file) => file.read_afresh_revision && file.source_id)
    .map((file) => ({
      batch_id: file.batch_id,
      source_id: file.source_id as string,
      expected_revision: file.read_afresh_revision as string,
    }))
  if (!files.length) return "No removed PDF is waiting to be read afresh"
  const result = readAfreshResponse.parse(
    await fetchAPI(`/api/financial/statement-import/review/read-afresh?case_id=${caseId}`, {
      method: "POST",
      body: { files },
      timeout: 300000,
    })
  )
  const parts = [`${result.queued} ${result.queued === 1 ? "PDF is" : "PDFs are"} being read afresh`]
  if (result.already) parts.push(`${result.already} already being read`)
  if (result.refused.length)
    parts.push(`${result.refused.length} not started: ${result.refused[0].message}`)
  return parts.join("; ")
}

const checkAgainResponse = z.object({
  requested: z.number(),
  queued: z.number(),
  skipped: z.array(z.object({ batch_id: z.string(), message: z.string() })),
})

/** Prepares the queue's unreadable statements' files again from their saved readings with the current reader. */
export async function checkUnreadableAgain(caseId: string, data: ReviewQueue): Promise<string> {
  const files = data.unreadable
    .filter((entry) => entry.batch_id)
    .map((entry) => ({ batch_id: entry.batch_id as string, file_id: entry.file_id }))
  if (!files.length) return "Nothing to check again"
  const result = checkAgainResponse.parse(
    await fetchAPI(`/api/financial/statement-import/review/check-again?case_id=${caseId}`, {
      method: "POST",
      body: { files },
      timeout: 120000,
    })
  )
  const parts = [`${result.queued} ${result.queued === 1 ? "file is" : "files are"} being checked again`]
  if (result.skipped.length) parts.push(`${result.skipped.length} ${result.skipped.length === 1 ? "batch" : "batches"} not started: ${result.skipped[0].message}`)
  return parts.join("; ")
}

/** Put a fund statement set aside as not a payment statement back for review (recorded as your decision). */
export async function putBackNotPaymentStatement(caseId: string, fileId: string, statementId?: string | null) {
  return fetchAPI(
    `/api/financial/statement-import/${encodeURIComponent(fileId)}/not-payment-statement?${new URLSearchParams({ case_id: caseId })}`,
    { method: "POST", body: { action: "restore", statement_id: statementId ?? null } }
  )
}

export type ProposalGroup = NonNullable<ReviewQueue["proposal_groups"]>[number]

const groupConfirmResponse = z.object({
  group_id: z.string(),
  field: z.string(),
  value: z.string(),
  statements: z.number(),
  saved: z.number(),
  failed: z.number(),
})

/** Confirms one account's proposed value on all its waiting statements (empty fields only), as this person. */
export async function confirmProposalGroup(caseId: string, group: ProposalGroup, fileIds: string[] = []) {
  return groupConfirmResponse.parse(
    await fetchAPI(`/api/financial/statement-import/review/proposal-groups/confirm?case_id=${caseId}`, {
      method: "POST",
      body: { group_id: group.id, file_ids: fileIds },
      timeout: 300000,
    })
  )
}
