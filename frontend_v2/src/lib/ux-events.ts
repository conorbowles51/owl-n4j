import { fetchAPI } from "@/lib/api-client"
import FIELDS from "./ux-event-fields.json"

/**
 * Phone screen instrumentation (07 section 10.2). Events carry ids, kinds, counts, milliseconds and booleans only;
 * the allowed fields are the one list in ux-event-fields.json, shared byte for byte with the backend
 * (services/ux_event_fields.json), and the backend refuses anything else. An event that fails here is not sent
 * at all, so a name, number, message text, address, coordinate or query string never leaves the browser.
 * Events go to Loupe's own records (/api/request-speed/ux-events); nothing goes to a third party.
 */

type FieldSpec = { enum?: string[]; ref?: string; int?: [number, number]; number?: [number, number]; bool?: boolean; uuid?: boolean }
const TYPES = FIELDS.field_types as Record<string, FieldSpec>
const EVENTS = FIELDS.events as Record<string, string[]>
const REQUIRED = FIELDS.required as Record<string, string[]>

export type UxEventName = keyof typeof FIELDS.events
export type UxEvent = { event: UxEventName } & Record<string, string | number | boolean>

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function fieldOk(name: string, value: unknown): boolean {
  let spec = TYPES[name]
  if (!spec) return false
  if (spec.ref) spec = TYPES[spec.ref]
  if (spec.enum) return typeof value === "string" && spec.enum.includes(value)
  if (spec.bool) return typeof value === "boolean"
  if (spec.int) return Number.isInteger(value) && (value as number) >= spec.int[0] && (value as number) <= spec.int[1]
  if (spec.number) return typeof value === "number" && Number.isFinite(value) && value >= spec.number[0] && value <= spec.number[1]
  if (spec.uuid) return typeof value === "string" && UUID.test(value)
  return false
}

/** Why an event is refused, or null when every field is allowed (the same rule as the backend's clean()). */
export function refusal(event: Record<string, unknown>): string | null {
  const allowed = EVENTS[event.event as string]
  if (!allowed) return "unknown event"
  for (const [name, value] of Object.entries(event)) {
    if (name === "event") continue
    if (!allowed.includes(name)) return `field ${name} is not allowed on ${event.event}`
    if (!fieldOk(name, value)) return `${name} is not an allowed value`
  }
  const missing = (REQUIRED[event.event as string] ?? []).filter((name) => !(name in event))
  return missing.length ? `${event.event} needs ${missing.join(", ")}` : null
}

const ENDPOINT = "/api/request-speed/ux-events"
const FLUSH_MS = 5000
const PER_POST = 50
let queue: { caseId: string | null; event: UxEvent }[] = []
let timer: ReturnType<typeof setTimeout> | null = null
let listening = false
let refusedHere = 0
let send: (body: { case_id: string | null; events: UxEvent[] }, keepalive: boolean) => void = (body, keepalive) => {
  void fetchAPI(ENDPOINT, { method: "POST", body, keepalive, priority: "low", timeout: 15000 }).catch(() => undefined)
}

/** Queue one event. Returns false (and sends nothing) when any field is outside the allowed list. */
export function trackUx(caseId: string | null, event: UxEvent): boolean {
  const why = refusal(event)
  if (why) {
    refusedHere += 1
    if (import.meta.env.DEV) console.warn(`ux event not sent: ${why}`)
    return false
  }
  const rounded = { ...event }
  if (typeof rounded.ms === "number") rounded.ms = Math.round(rounded.ms)
  queue.push({ caseId: caseId && UUID.test(caseId) ? caseId : null, event: rounded })
  if (!listening && typeof window !== "undefined") {
    listening = true
    window.addEventListener("pagehide", () => flushUx(true))
  }
  if (queue.length >= PER_POST) flushUx()
  else if (!timer) timer = setTimeout(() => flushUx(), FLUSH_MS)
  return true
}

export function flushUx(keepalive = false) {
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
  while (queue.length) {
    const caseId = queue[0].caseId
    const run: UxEvent[] = []
    while (queue.length && queue[0].caseId === caseId && run.length < PER_POST) run.push(queue.shift()!.event)
    send({ case_id: caseId, events: run }, keepalive)
  }
}

/** A journey's clock: start, steps and completion or abandonment, each with milliseconds since the start. */
export function startJourney(caseId: string | null, journey: string, screen: string, now: () => number = () => performance.now()) {
  const began = now()
  let step = 0
  let actions = 0
  let ended = false
  trackUx(caseId, { event: "journey_start", journey, screen })
  return {
    action() {
      actions += 1
    },
    step(at: string) {
      if (ended) return
      step += 1
      trackUx(caseId, { event: "journey_step", journey, step, screen: at, ms: now() - began })
    },
    complete() {
      if (ended) return
      ended = true
      trackUx(caseId, { event: "journey_complete", journey, ms: now() - began, actions })
    },
    abandon() {
      if (ended) return
      ended = true
      trackUx(caseId, { event: "journey_abandon", journey, step: Math.max(1, step), ms: now() - began })
    },
  }
}

export function resetUxForTest(sender?: typeof send) {
  queue = []
  if (timer) clearTimeout(timer)
  timer = null
  refusedHere = 0
  if (sender) send = sender
}

export function refusedCountForTest() {
  return refusedHere
}
