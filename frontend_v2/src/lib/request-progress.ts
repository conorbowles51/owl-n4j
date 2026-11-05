import { parseJSONSliced, yieldToBrowser } from "./sliced-json"

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
  /** After the bytes are in: the answer being unpacked (rows of rows, or characters looked through of all). */
  unpack?: { done: number; total: number; unit: "characters" | "rows"; started: number } | null
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
  ["/api/financial/ledger-overview-panel-figures", "the overview panels"],
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
  ["/api/evidence-folders", "evidence folders"],
  ["/api/evidence-folders/search", "evidence search results"],
  ["/api/graph", "the graph"],
  ["/api/graph/node", "node details"],
  ["/api/graph/locations", "located entities"],
  ["/api/graph/locations/needs-review", "locations needing review"],
  ["/api/phones/map", "phone positions"],
  ["/api/timeline", "timeline events"],
  ["/api/timeline/entries", "timeline additions"],
  ["/api/timeline/views", "timeline views"],
  ["/api/cases", "cases"],
  ["/api/users", "users"],
  ["/api/profiles", "processing profiles"],
  ["/api/background-tasks", "background tasks"],
  ["/api/system-logs", "system logs"],
  ["/api/admin/ai-costs", "AI costs"],
  ["/api/snapshots", "snapshots"],
  ["/api/triage/cases", "triage cases"],
  ["/api/workspace", "the workspace"],
  ["/api/auth/me", "your sign-in"],
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
    unpack: null,
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

export function unpackProgress(id: number, done: number, total: number, unit: "characters" | "rows") {
  const request = requests.get(id)
  if (!request) return
  // When this unit started (a rate for time left is measured within one unit only).
  const started = request.unpack?.unit === unit ? request.unpack.started : now()
  request.unpack = { done, total, unit, started }
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

const READ_BUDGET_MS = 25
const clock = () => (typeof performance !== "undefined" ? performance.now() : Date.now())

/** Reads a JSON answer, counting its bytes against `id` as they arrive when it is large enough to be worth it. */
export async function readJSON<T>(response: Response, id: number): Promise<T> {
  const total = bodyLength(response)
  if (!response.body || total === null || total < COUNTED_MINIMUM || typeof TextDecoder === "undefined") {
    const value = (await response.json()) as T
    if (total !== null) receiveBytes(id, total)
    return value
  }
  const reader = response.body.getReader()
  // Decoded as it arrives (a character cut between chunks is held until its last byte), then unpacked in pieces
  // so the page can redraw its loading panel while a large answer is parsed (lib/sliced-json.ts).
  const decoder = new TextDecoder()
  const parts: string[] = []
  // A read of bytes that have already arrived resolves without giving the browser a turn, so after a busy spell
  // the whole buffered answer was decoded in one step (d5b330d1 People, 61 MB, 1 Nov: up to 1,001 ms after a
  // release). The decoding gives the browser a turn every READ_BUDGET_MS, as the unpacking does.
  let since = clock()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    if (value) {
      parts.push(decoder.decode(value, { stream: true }))
      receiveBytes(id, value.byteLength)
    }
    if (clock() - since >= READ_BUDGET_MS) {
      await yieldToBrowser()
      since = clock()
    }
  }
  parts.push(decoder.decode())
  const text = parts.join("")
  parts.length = 0
  return parseJSONSliced<T>(text, (done, of, unit) => unpackProgress(id, done, of, unit))
}

/** Test hook: forget every recorded read. */
export function resetRequestsForTest() {
  requests.clear()
  nextId = 1
  changed()
}
