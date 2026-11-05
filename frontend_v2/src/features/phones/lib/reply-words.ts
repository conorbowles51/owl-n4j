import type { ReplyLink, StreamRow } from "../schemas"
import { labelText } from "./labels"

/**
 * A reply, quote or forward in words (03 section 6.6), the same on the row, in a copy and in the PDF export. A
 * forward's author is named apart from the row's sender: the sender sent this copy, the author first wrote it.
 */

export function replyVerb(r: ReplyLink): string {
  return r.kind === "quote" ? "Quoting" : "Replying to"
}

export function replyWhere(r: ReplyLink): string {
  const t = r.target
  if (!t || t.same_thread) return ""
  return ` in ${t.thread_title ?? "another conversation"}`
}

export function replyWords(r: ReplyLink): string {
  if (r.target) return `${replyVerb(r)} ${labelText(r.target.from)}, ${r.target.time}${replyWhere(r)}: ${r.target.excerpt ?? "(no text)"}${r.target.chars > (r.target.excerpt?.length ?? 0) ? "…" : ""}`
  if (r.state === "not_in_extraction") return `${replyVerb(r)} a message that is not in this extraction (the report's id: ${r.original_id})`
  return "Marked as a reply; the report does not say to which message"
}

export function forwardWords(row: StreamRow): string | null {
  const f = row.forward
  if (!f) return null
  if (!f.original_sender) return "Forwarded. The report does not say who first wrote it"
  return `Forwarded. First written by ${labelText(f.original_sender)}${f.time_created ? `, ${f.time_created}` : ""}`
}
