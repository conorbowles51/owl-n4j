import type { Scope } from "./api"

/** The Timeline's dragged range or date range as a selection (lx-corrorest B): the events inside it, with the window. */
export interface TimelineRange {
  from: string | null
  to: string | null
}

/** A window's start and end as the scope's whole days. Only the date part is kept: the scope works in days. */
export function rangeScope(range: TimelineRange): Scope {
  const day = (v: string | null) => (v && /^\d{4}-\d{2}-\d{2}/.test(v) ? v.slice(0, 10) : undefined)
  const from = day(range.from)
  const to = day(range.to)
  return { ...(from ? { from } : {}), ...(to ? { to } : {}) }
}

export function rangeWords(range: TimelineRange): string {
  const s = rangeScope(range)
  const span = s.from || s.to ? `${s.from ?? "the start"} to ${s.to ?? "the end"}` : "everything shown"
  return `Timeline ${span}, events`
}
