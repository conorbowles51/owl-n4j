/**
 * What the page's API reads are doing right now, from true counts only: each GET started through fetchAPI is
 * recorded with when it started, when its answer began, the bytes read so far and the answer's own length
 * (the server's X-Body-Length, the uncompressed size; absent when the length is not known up front). The
 * loading panel (features/financial/components/LoadProgress.tsx) reads this; nothing here is timer-driven.
 * Uses only performance.now and fetch streams (safe over plain http).
 */

export interface RequestState {
  id: number
  endpoint: string
  /** Plain words for what the read is, e.g. "payments". */
  what: string
  started: number
  /** performance.now when the answer's headers arrived (the server finished working it out). */
  answered: number | null
  received: number
  total: number | null
  ended: number | null
  failed: string | null
}

const requests = new Map<number, RequestState>()
const listeners = new Set<() => void>()
let nextId = 1
let version = 0
const KEEP_ENDED = 200

const now = () => (typeof performance !== "undefined" ? performance.now() : Date.now())

function changed() {
  version += 1
  for (const listener of listeners) listener()
}

/** Called on every change (start, answer, bytes, end). */
export function subscribeRequests(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function requestsVersion() {
  return version
}

/** Every recorded read started at or after `since` (performance.now), oldest first. */
export function requestsSince(since: number): RequestState[] {
  return [...requests.values()].filter((request) => request.started >= since)
}

// Path pieces in plain words. The first match of the longest prefix wins; anything else is worded from its last
// path segment ("ledger-accounts" -> "ledger accounts").
const WORDS: [string, string][] = [
  ["/api/financial/ledger-first-view", "the payments overview"],
  ["/api/financial/ledger-overview-panels", "the overview panels"],
  ["/api/financial/ledger-overview", "the overview"],
  ["/api/financial/ledger-working-summary", "the working summary"],
  ["/api/financial/ledger-working-analysis", "the working analysis"],
  ["/api/financial/ledger-summary", "the ledger summary"],
  ["/api/financial/ledger-accounts", "accounts"],
  ["/api/financial/ledger-trends", "trends"],
  ["/api/financial/ledger-counterparties", "people and businesses"],
  ["/api/financial/ledger-categories", "categories"],
  ["/api/financial/ledger-count", "the payment count"],
  ["/api/financial/ledger-timeline", "the timeline"],
  ["/api/financial/ledger-posting-graph", "the money flow"],
  ["/api/financial/ledger-transfer-candidates", "possible transfers"],
  ["/api/financial/ledger/category-library", "the category list"],
  ["/api/financial/ledger/category-breakdown", "the category breakdown"],
  ["/api/financial/ledger", "payments"],
  ["/api/financial/account-history", "account history"],
  ["/api/financial/account-parties", "account holders"],
  ["/api/financial/account-references", "account references"],
  ["/api/financial/counterparty-parties", "people and businesses"],
  ["/api/financial/counterparty-party-analysis", "people and businesses"],
  ["/api/financial/money-trails", "money trails"],
  ["/api/financial/judgements", "judgement calls"],
  ["/api/financial/review/queue", "the statements queue"],
  ["/api/financial/review", "statement review"],
  ["/api/financial/statement-import/files", "statement files"],
  ["/api/financial/statement-import/incomplete-records", "incomplete records"],
  ["/api/financial/statement-import", "statements"],
  ["/api/financial/batches", "statement batches"],
  ["/api/financial/categories", "categories"],
  ["/api/financial/summary", "the summary"],
  ["/api/financial/entities", "names"],
  ["/api/evidence", "evidence files"],
]

export function requestWords(endpoint: string): string {
  const path = endpoint.split("?")[0].split("#")[0]
  let best: [string, string] | null = null
  for (const entry of WORDS) {
    const [prefix] = entry
    // Whole path segments only: "/api/financial/ledger" matches ".../ledger/sources", never ".../ledger-accounts".
    if ((path === prefix || path.startsWith(`${prefix}/`)) && (!best || prefix.length > best[0].length)) best = entry
  }
  if (best) return best[1]
  if (path === "/api/financial") return "payments"
  const segment = path.split("/").filter(Boolean).pop() ?? "data"
  return /^[0-9a-f-]{8,}$/i.test(segment) ? "details" : segment.replace(/[-_]+/g, " ")
}

export function startRequest(endpoint: string): number {
  const id = nextId++
  requests.set(id, {
    id,
    endpoint,
    what: requestWords(endpoint),
    started: now(),
    answered: null,
    received: 0,
    total: null,
    ended: null,
    failed: null,
  })
  if (requests.size > KEEP_ENDED) {
    for (const [key, request] of requests) {
      if (requests.size <= KEEP_ENDED) break
      if (request.ended !== null) requests.delete(key)
    }
  }
  changed()
  return id
}

export function answerRequest(id: number, total: number | null) {
  const request = requests.get(id)
  if (!request) return
  request.answered = now()
  request.total = total !== null && Number.isFinite(total) && total >= 0 ? total : null
  changed()
}

export function receiveBytes(id: number, bytes: number) {
  const request = requests.get(id)
  if (!request) return
  request.received += bytes
  changed()
}

export function endRequest(id: number, failed: string | null) {
  const request = requests.get(id)
  if (!request || request.ended !== null) return
  request.ended = now()
  request.failed = failed
  changed()
}

/** The answer's own length (X-Body-Length), or null when the server did not say. */
export function bodyLength(response: Response): number | null {
  const value = response.headers.get("x-body-length")
  if (value === null || !/^\d+$/.test(value)) return null
  return Number(value)
}

// Answers at least this large are read as a stream so their bytes can be counted as they arrive.
export const COUNTED_MINIMUM = 64 * 1024

/** Reads a JSON answer, counting its bytes against `id` as they arrive when it is large enough to be worth it. */
export async function readJSON<T>(response: Response, id: number): Promise<T> {
  const total = bodyLength(response)
  if (!response.body || total === null || total < COUNTED_MINIMUM || typeof TextDecoder === "undefined") {
    const value = (await response.json()) as T
    if (total !== null) receiveBytes(id, total)
    return value
  }
  const reader = response.body.getReader()
  const chunks: Uint8Array[] = []
  let size = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    if (value) {
      chunks.push(value)
      size += value.byteLength
      receiveBytes(id, value.byteLength)
    }
  }
  const whole = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) {
    whole.set(chunk, offset)
    offset += chunk.byteLength
  }
  chunks.length = 0
  return JSON.parse(new TextDecoder().decode(whole)) as T
}

/** Test hook: forget every recorded read. */
export function resetRequestsForTest() {
  requests.clear()
  nextId = 1
  changed()
}
