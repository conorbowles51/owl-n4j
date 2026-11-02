import type { UseStream } from "../hooks/use-stream"

export const LONG_BODY = 2000
export const STALE_COPY = "New data arrived while the rows were loading. Nothing was copied; the list has been refreshed, copy again."

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
