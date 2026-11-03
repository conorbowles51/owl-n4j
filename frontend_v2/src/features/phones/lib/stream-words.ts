import type { UseStream } from "../hooks/use-stream"

export const LONG_BODY = 2000
export const STALE_COPY = "New data arrived while the rows were loading. Nothing was copied; the list has been refreshed, copy again."
export const STALE_AFTER_COPY = "New data arrived after these rows were loaded, so what was just copied may be out of date. The list has been refreshed; copy again."

export function plural(n: number, noun: { one: string; many: string }) {
  return `${n.toLocaleString("en-US")} ${n === 1 ? noun.one : noun.many}`
}

export function totalWords(stream: UseStream, noun: { one: string; many: string }): string {
  const c = stream.index?.counts
  if (!c) return ""
  const base = plural(c.events, noun)
  const incomplete = stream.index && !stream.index.complete ? " (incomplete)" : ""
  if (c.collapsed_copies > 0) {
    const copies = c.collapsed_copies === 1 ? "1 repeated copy" : `${c.collapsed_copies.toLocaleString("en-US")} repeated copies`
    return `${base} (${c.records.toLocaleString("en-US")} records; ${copies} shown once)${incomplete}`
  }
  return base + incomplete
}

/** The undated group's header (03 C-3 and 07 J-4): "No time recorded. 6 messages have no time and are listed at the end." */
export function undatedWords(n: number, noun: { one: string; many: string }, position: "first" | "last"): string {
  return `No time recorded. ${undatedSentence(n, noun, position)}`
}

/** "6 messages have no time and are listed at the end.": also beside the list's total, so the undated messages are
 * counted where the reader starts, not only at the far end of the list (07 J-4). */
export function undatedSentence(n: number, noun: { one: string; many: string }, position: "first" | "last"): string {
  return `${plural(n, noun)} ${n === 1 ? "has" : "have"} no time and ${n === 1 ? "is" : "are"} listed at the ${position === "first" ? "start" : "end"}.`
}
