import type { RequestState } from "@/lib/request-progress"

/** Pure parts of the loading panel (components/LoadProgress.tsx): what the reads say, sizes, recorded load times. */

export const TICK_MS = 500
export const STALL_MS = 3000
export const SLOW_MS = 10000
export const SHOW_AFTER_MS = 300
const RECORD_PREFIX = "loupe:view-load-ms:"

const recordKey = (caseId: string, page: string) => `${RECORD_PREFIX}${caseId}:${page}`

export function recordedMs(caseId: string, page: string): number | null {
  try {
    const value = Number(localStorage.getItem(recordKey(caseId, page)))
    return Number.isFinite(value) && value > 0 ? value : null
  } catch {
    return null
  }
}

export function saveMs(caseId: string, page: string, ms: number) {
  try {
    localStorage.setItem(recordKey(caseId, page), String(Math.round(ms)))
  } catch {
    // Private mode or a full store: the next load shows completion without a time estimate.
  }
}

const MB = 1024 * 1024
export function sizeWords(bytes: number) {
  if (bytes >= MB) return `${(bytes / MB).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

export const seconds = (ms: number) => Math.max(1, Math.round(ms / 1000))

export interface LoadPicture {
  /** Words for what is happening now. */
  step: string
  /** Parts done of parts asked for (+1 for drawing the page), with received bytes counted as a fraction. */
  done: number
  total: number
  partsDone: number
  partsAsked: number
  bytes: { received: number; total: number } | null
  current: RequestState | null
  failed: RequestState[]
}

/**
 * Reads that failed and have not since been asked again: a later read of the same address that is still running or
 * that succeeded (a retry, React Query's own or the person's) settles the failure. Each address is named once.
 */
export function unresolvedFailures(reads: RequestState[]): RequestState[] {
  const latest = new Map<string, RequestState>()
  for (const read of reads) {
    const held = latest.get(read.endpoint)
    if (!held || read.started >= held.started) latest.set(read.endpoint, read)
  }
  return [...latest.values()].filter((read) => read.ended !== null && read.failed)
}

/** What the reads say right now (pure: tested directly). */
export function picture(reads: RequestState[]): LoadPicture {
  const failed = unresolvedFailures(reads)
  const pending = reads.filter((read) => read.ended === null)
  let done = 0
  for (const read of reads) {
    if (read.ended !== null) done += 1
    else if (read.total) done += Math.min(read.received / read.total, 0.99)
  }
  // The part to talk about: an answer arriving now (largest first), else the read waiting longest.
  const receiving = pending
    .filter((read) => read.answered !== null && read.total)
    .sort((a, b) => (b.total ?? 0) - (a.total ?? 0))
  const current = receiving[0] ?? [...pending].sort((a, b) => a.started - b.started)[0] ?? null
  let step: string
  if (!reads.length) step = "Opening this page"
  else if (!current) step = "Drawing the page"
  else if (current.answered === null) step = `Working out ${current.what} on the server`
  else step = `Receiving ${current.what}`
  return {
    step,
    done,
    total: reads.length + 1,
    partsDone: reads.filter((read) => read.ended !== null).length,
    partsAsked: reads.length,
    bytes: current?.answered !== null && current?.total ? { received: current.received, total: current.total } : null,
    current,
    failed,
  }
}

