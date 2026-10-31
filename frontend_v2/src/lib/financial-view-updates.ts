/**
 * Financial views answered with their previous copy while the server computes them again after a change.
 *
 * A Financial GET says it can show such an answer (ACCEPT_HEADER). The server then answers a view whose rows have
 * changed since it was computed with that earlier copy, marked updating with the time it is from (STATE_HEADER,
 * AS_OF_HEADER), instead of making the person wait for the computation. fetchAPI records every such answer here by
 * its request address, and clears it when the same address next answers current, whatever the query does with
 * the data. The Financial page shows plainly that what it shows is being updated while any of its addresses is
 * recorded (FinancialViewUpdatingNotice), so nothing marked updating is ever shown as current.
 */
export const ACCEPT_HEADER = "X-Financial-View-Accept"
export const STATE_HEADER = "X-Financial-View-State"
export const AS_OF_HEADER = "X-Financial-View-As-Of"

/**
 * After this tab changes anything, its reads wait for current answers for this long: an editor that reads a
 * revision back after its own save must never be given the copy from before that save.
 */
export const AFTER_OWN_WRITE_MS = 120000
let ownWriteAt = -Infinity

/** Called for every successful write this tab makes. */
export function noteOwnWrite(now = Date.now()) {
  ownWriteAt = now
}

/**
 * Requests that change nothing a Financial view shows: the page's own speed records (posted every few seconds
 * while the page is used) and signing in or out. Counting them as this tab's writes kept updating answers off
 * for people using the page (live 2026-10-31 12:24: an evidence list computed inline for 7.6 s right after a
 * speed record was posted).
 */
const NOT_DATA_WRITES = ["/api/request-speed/", "/api/auth/"]

/** True when a successful request with this method may have changed what a Financial view shows. */
export function isOwnWrite(endpoint: string, method?: string) {
  const verb = (method ?? "GET").toUpperCase()
  return verb !== "GET" && verb !== "HEAD" && !NOT_DATA_WRITES.some((prefix) => endpoint.startsWith(prefix))
}

/** Financial reads that may be answered as updating. */
export function acceptsUpdating(endpoint: string, method?: string, now = Date.now()) {
  return (
    (method ?? "GET").toUpperCase() === "GET" &&
    now - ownWriteAt >= AFTER_OWN_WRITE_MS &&
    (endpoint.startsWith("/api/financial") ||
      (endpoint.startsWith("/api/evidence?") && endpoint.includes("financial_only=true")))
  )
}

/** The as-of time of an updating answer, or undefined when the response is current. */
export function updatingAsOf(response: Response): string | undefined {
  if (response.headers.get(STATE_HEADER) !== "updating") return undefined
  return response.headers.get(AS_OF_HEADER) || ""
}

let updating: ReadonlyMap<string, string> = new Map()
const listeners = new Set<() => void>()
let sequence = 0
const latestAnswered = new Map<string, number>()

/** A number for a request as it starts; answers are recorded in the order their requests started. */
export function nextRequestNumber() {
  sequence += 1
  return sequence
}

/**
 * Records how this address last answered: updating from ``asOf``, or current (undefined). ``request``: the
 * number its request was given when it started; an answer to an earlier request than one already recorded is
 * ignored (two workers can answer out of order).
 */
export function noteViewAnswer(endpoint: string, asOf: string | undefined, request = nextRequestNumber()) {
  if ((latestAnswered.get(endpoint) ?? 0) > request) return
  latestAnswered.set(endpoint, request)
  if (asOf === undefined ? !updating.has(endpoint) : updating.get(endpoint) === asOf) return
  const next = new Map(updating)
  if (asOf === undefined) next.delete(endpoint)
  else next.set(endpoint, asOf)
  updating = next
  listeners.forEach((listener) => listener())
}

/** Addresses whose last answer was updating, with the time each copy is from. */
export function updatingViews(): ReadonlyMap<string, string> {
  return updating
}

export function subscribeUpdatingViews(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Forget every record (sign-out, tests). */
export function clearUpdatingViews() {
  latestAnswered.clear()
  ownWriteAt = -Infinity
  if (updating.size === 0) return
  updating = new Map()
  listeners.forEach((listener) => listener())
}
