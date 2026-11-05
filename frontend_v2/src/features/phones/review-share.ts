import { ApiError, fetchAPI } from "@/lib/api-client"
import { failureText, type StreamFilter } from "./api"

/** A refusal's own reason: these routes answer with a sentence in ``detail`` (a 409 or 422 says why). */
export function shareFailure(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const d = (error.data as { detail?: unknown } | undefined)?.detail
    if (typeof d === "string" && d.trim()) return d
  }
  return failureText(error, fallback)
}

/** Sharing a phone review across people (07 J-13 steps 1, 5 and 6 and "[name] is also reviewing this thread."). */

export type SplitBy = "thread" | "person"

export interface SplitPart {
  part: number
  reviewer: { user_id: string; name: string }
  threads: number
  messages: number
  people: number
  words: string
}

export interface SplitPlan {
  by: SplitBy
  only_not_reviewed: boolean
  threads_in_filter: number
  threads: number
  messages: number
  already_reviewed_left_out: number
  already_in_a_task_left_out?: number
  parts: SplitPart[]
  words: string
  warning: string | null
}

export interface SplitMade {
  split_id: string
  tasks: { task_id: string; title: string; reviewer: { user_id: string; name: string }; threads: number; messages: number }[]
  threads: number
  words: string
}

interface SplitRequest {
  filter: StreamFilter
  by: SplitBy
  reviewers: string[]
  only_not_reviewed: boolean
  scope_words?: string
}

export function previewSplit(body: SplitRequest) {
  return fetchAPI<SplitPlan>("/api/phones/conversations/review/split/preview", { method: "POST", body })
}

/** Makes the tasks; 409 when the threads changed since the counts were shown (nothing is made). */
export function makeSplit(body: SplitRequest & { expect_threads: number }) {
  return fetchAPI<SplitMade>("/api/phones/conversations/review/split", { method: "POST", body })
}

export interface SecondPassMade {
  pass_id: string
  task_id: string
  title: string
  seed: number
  percent: number
  sample: number
  eligible: number
  words: string
}

export function startSecondPass(caseId: string, reviewer: string, percent = 10) {
  return fetchAPI<SecondPassMade>("/api/phones/conversations/review/second-pass", {
    method: "POST",
    body: { case_id: caseId, reviewer, percent },
  })
}

export interface SecondPassState {
  first: { reviewed_by?: string; reviewed_by_name?: string; reviewed_at?: string; record_count?: number }
  result: { agrees: boolean; note: string | null; by_name: string; at: string } | null
  earlier_results: number
  assigned_to: string | null
  assigned_to_name: string | null
  seed: number
  percent: number
  words: string
  task_id: string
  title: string
  mine: boolean
  status: string
  position?: ReviewPosition | null
}

export function recordSecondPass(caseId: string, taskId: string, threadKey: string, agrees: boolean, note: string) {
  return fetchAPI<SecondPassState>("/api/phones/conversations/review/second-pass/result", {
    method: "POST",
    body: { case_id: caseId, task_id: taskId, thread_key: threadKey, agrees, note: note.trim() || null },
  })
}

export interface ReviewPosition {
  event_uid: string
  instant: string | null
  by_name: string
  at: string
}

export interface ThreadReviewState {
  thread_key: string
  tasks: { task_id: string; title: string; assigned_to_name: string | null; mine: boolean; status: string; position?: ReviewPosition | null }[]
  second_pass: SecondPassState[]
}

/** The position of an assigned review, kept on the task's link (07 J-15 step 2). */
export function saveReviewPosition(caseId: string, threadKey: string, position: { event_uid: string; instant: string | null }) {
  return fetchAPI<{ saved: number }>("/api/phones/conversations/review/position", {
    method: "POST",
    body: { case_id: caseId, thread_key: threadKey, position },
  })
}

export interface ContinueThread {
  thread_key: string
  title: string | null
  extraction_id: string
  open: string
  position: ReviewPosition | null
}

export interface ContinueWork {
  assigned: { task_id: string; title: string; kind: "threads" | "readings"; total: number; open: number; phones: string[]; items: ContinueThread[]; next: ContinueThread[] }[]
  reading: { thread_key: string; title: string; phone: string; extraction_id: string; record: string | null }[]
}

export function getContinueWork(caseId: string, threads: { thread: string; record: string | null }[]) {
  return fetchAPI<ContinueWork>("/api/phones/conversations/review/continue", { method: "POST", body: { case_id: caseId, threads } })
}

export interface HandedOver {
  note_id: string
  open_items: number
  positions: number
  words: string
}

/** Reassigns a review task and attaches a Workspace note listing positions and open items (07 J-15 step 4). */
export function handOverReview(caseId: string, taskId: string, toUser: string, note: string) {
  return fetchAPI<HandedOver>(`/api/phones/conversations/review/tasks/${encodeURIComponent(taskId)}/hand-over`, {
    method: "POST",
    body: { case_id: caseId, to_user: toUser, note: note.trim() || null },
  })
}

export function getThreadReviewState(caseId: string, threadKey: string) {
  return fetchAPI<ThreadReviewState>(
    `/api/phones/conversations/review/thread?case_id=${encodeURIComponent(caseId)}&thread_key=${encodeURIComponent(threadKey)}`,
  )
}

export interface PresenceBeat {
  thread_key: string
  others: string[]
  words: string | null
  next_in_seconds: number
}

export function presenceBeat(caseId: string, threadKey: string, leaving = false) {
  return fetchAPI<PresenceBeat>("/api/phones/conversations/presence", {
    method: "POST",
    body: { case_id: caseId, thread_key: threadKey, leaving },
  })
}

export interface CoverageThread {
  thread_key: string
  title: string
  phone: string
  messages: number
  review: string | null
  added_since: number | null
}

export interface ReviewCoverageSummary {
  counts: { threads: number; reviewed: number; partly_reviewed: number; not_reviewed: number; never_reviewed: number }
  words: string
  reviewers: { name: string; reviewed: number; partly_reviewed: number; messages_at_review: number }[]
  not_reviewed: CoverageThread[]
  partly_reviewed: CoverageThread[]
  reviewed: CoverageThread[]
  splits: { task_id: string; title: string; status: string; reviewer: string | null; threads: number; reviewed: number; words: string }[]
  second_pass: {
    pass_id: string
    task_id: string
    title: string
    seed: number
    percent: number
    eligible: number
    reviewer: string | null
    sampled: number
    agrees: number
    disagrees: number
    pending: number
    disagreements: { thread_key: string; title: string; by: string; first_by: string | null; note: string }[]
  }[]
  reading_rechecks?: null | { sampled: number; agrees: number; disagrees: number; pending: number; rate_percent: number | null; too_few: boolean; words: string }
  searches: { query: string; exact: boolean; runs: number; people: string[]; surfaces: string[]; last_hits: number | null; last_run_at: string }[]
  keyword_lists: { name: string; terms: string[] }[]
  terms: string[]
  cover: string[]
}

export function getReviewCoverage(caseId: string, phones: string[] = []) {
  const p = new URLSearchParams({ case_id: caseId })
  if (phones.length) p.set("phones", phones.join(","))
  return fetchAPI<ReviewCoverageSummary>(`/api/phones/conversations/review/coverage?${p.toString()}`)
}
