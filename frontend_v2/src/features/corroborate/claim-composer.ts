/** Opening the claim composer from any screen (a theory line, a statement line): ``openClaimComposer({ text, ... })``. */
export interface ClaimComposerRequest {
  text: string
  statementDate?: string
  speaker?: string
  source?: Record<string, unknown>
}
export const CLAIM_EVENT = "corroborate:claim"
export function openClaimComposer(detail: ClaimComposerRequest) {
  window.dispatchEvent(new CustomEvent<ClaimComposerRequest>(CLAIM_EVENT, { detail }))
}

/** An instant shown in the case's zone as "YYYY-MM-DDTHH:mm" for a datetime-local input. */
export function toZoneInput(iso: string, zone: string): string {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: zone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
    .formatToParts(new Date(iso)).map((x) => [x.type, x.value]))
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`
}

/** The inverse: a zone's wall-clock "YYYY-MM-DDTHH:mm" as an ISO instant. */
export function fromZoneInput(local: string, zone: string): string {
  const asUtc = Date.parse(local + ":00Z")
  let guess = asUtc
  for (let i = 0; i < 2; i++) {
    const shown = Date.parse(toZoneInput(new Date(guess).toISOString(), zone) + ":00Z")
    guess += asUtc - shown
  }
  return new Date(guess).toISOString()
}
