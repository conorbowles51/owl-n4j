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

/** Financial reads that may be answered as updating. */
export function acceptsUpdating(endpoint: string, method?: string) {
  return (
    (method ?? "GET").toUpperCase() === "GET" &&
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

/** Records how this address last answered: updating from ``asOf``, or current (undefined). */
export function noteViewAnswer(endpoint: string, asOf: string | undefined) {
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
  if (updating.size === 0) return
  updating = new Map()
  listeners.forEach((listener) => listener())
}
