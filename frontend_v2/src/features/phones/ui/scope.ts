import type { Scope, ParticipantMode } from "./ScopeBar"

export const EMPTY_SCOPE: Scope = { people: [], mode: "involving", phones: [], window: null, labels: [], kinds: [] }

export const MODE_WORDS: Record<ParticipantMode, string> = {
  involving: "Involving",
  between: "Between",
  "sent-by": "Sent by",
  "sent-to": "Sent to",
}

export function scopeWords(scope: Scope): string {
  const parts: string[] = []
  if (scope.people.length) {
    const names = scope.people.map((p) => p.label)
    parts.push(scope.mode === "between" ? `between ${names.join(" and ")}` : `${MODE_WORDS[scope.mode].toLowerCase()} ${names.join(", ")}`)
  }
  if (scope.window) parts.push(`${scope.window.from} to ${scope.window.to}`)
  if (scope.phones.length) parts.push(`on ${scope.phones.length} ${scope.phones.length === 1 ? "phone" : "phones"}`)
  if (scope.labels.length) parts.push(`labelled ${scope.labels.map((l) => l.label).join(", ")}`)
  if (scope.kinds.length) parts.push(scope.kinds.join(", "))
  return parts.join(", ") || "everything on every phone"
}

/** URL form (ids only; labels are looked up again on load). */
export function scopeToSearch(scope: Scope): string {
  const q = new URLSearchParams()
  if (scope.people.length) q.set("people", scope.people.map((p) => p.key).join(","))
  if (scope.mode !== "involving") q.set("mode", scope.mode)
  if (scope.phones.length) q.set("phones", scope.phones.map((p) => p.id).join(","))
  if (scope.window) q.set("window", `${scope.window.from}..${scope.window.to}`)
  if (scope.labels.length) q.set("labels", scope.labels.map((l) => l.id).join(","))
  if (scope.kinds.length) q.set("kinds", scope.kinds.join(","))
  return q.toString()
}

export function searchToScopeIds(search: string) {
  const q = new URLSearchParams(search)
  const list = (k: string) => (q.get(k) ? q.get(k)!.split(",").filter(Boolean) : [])
  const [from, to] = (q.get("window") ?? "").split("..")
  return {
    people: list("people"),
    mode: (q.get("mode") as ParticipantMode) ?? "involving",
    phones: list("phones"),
    window: from && to ? { from, to } : null,
    labels: list("labels"),
    kinds: list("kinds"),
  }
}

/** The URL parameters a scope is carried in between screens, the names Conversations reads (03 6.4). */
export const SCOPE_PARAMS = ["people", "mode", "phones", "from", "to", "kinds"] as const

export function scopeToParams(scope: Scope): Record<string, string> {
  const out: Record<string, string> = {}
  if (scope.people.length) out.people = scope.people.map((p) => p.key).join(",")
  if (scope.people.length && scope.mode !== "involving") out.mode = scope.mode
  if (scope.phones.length) out.phones = scope.phones.map((p) => p.id).join(",")
  if (scope.window?.from) out.from = scope.window.from
  if (scope.window?.to) out.to = scope.window.to
  if (scope.kinds.length) out.kinds = scope.kinds.join(",")
  return out
}

/** A screen's address with the scope in it, the receiving screen showing the same chips (07 4.5). */
export function scopeHref(path: string, scope: Scope, extra: Record<string, string> = {}): string {
  const q = new URLSearchParams({ ...extra, ...scopeToParams(scope) }).toString()
  return q ? `${path}?${q}` : path
}

export function paramsToScopeIds(search: string) {
  const q = new URLSearchParams(search)
  const list = (k: string) => (q.get(k) ? q.get(k)!.split(",").filter(Boolean) : [])
  const from = q.get("from")
  const to = q.get("to")
  const mode = q.get("mode")
  return {
    people: list("people"),
    mode: (mode === "between" || mode === "sent-by" || mode === "sent-to" ? mode : "involving") as ParticipantMode,
    phones: list("phones"),
    window: from || to ? { from: from ?? to!, to: to ?? from! } : null,
    labels: list("labels"),
    kinds: list("kinds"),
  }
}

/** Remembered per case for the session; storage failures never break the page (07 4.2 item 13). */
export function rememberScope(caseId: string, scope: Scope) {
  if (!scopeToSearch(scope)) return // "everything" is the screen's start, not a selection to bring back
  try {
    sessionStorage.setItem(`phone-scope:${caseId}`, JSON.stringify(scope))
    const recentKey = `phone-scope-recent:${caseId}`
    const recent: Scope[] = JSON.parse(sessionStorage.getItem(recentKey) ?? "[]")
    const key = scopeToSearch(scope)
    const next = [scope, ...recent.filter((s) => scopeToSearch(s) !== key)].slice(0, 5)
    sessionStorage.setItem(recentKey, JSON.stringify(next))
  } catch {
    /* storage unavailable: the URL still carries the scope */
  }
}

export function recallScope(caseId: string): { last: Scope | null; recent: Scope[] } {
  try {
    const last = sessionStorage.getItem(`phone-scope:${caseId}`)
    const recent = sessionStorage.getItem(`phone-scope-recent:${caseId}`)
    return { last: last ? JSON.parse(last) : null, recent: recent ? JSON.parse(recent) : [] }
  } catch {
    return { last: null, recent: [] }
  }
}
