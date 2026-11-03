import { participantsLine, type PhoneRecordView } from "../types"
import { instantWords } from "../lib/time-words"
import { originWords } from "./origin-words"

/**
 * The record panel's content (07 5, 03 3.6): the record in full with its time in words, both sides as
 * "Name (number)", origin mark and badges; actions Add to…, Around this time, Open the window around this,
 * Correct this value; and "Used in this case" (the reverse lookup). Shown inside DockedPanel.
 */
export function recordCopyText(r: PhoneRecordView): string {
  const when = r.time ? instantWords(r.time, r.zone, true) : "No time recorded"
  const mark = originWords(r.origin)
  const lines = [`${r.typeWords} on ${r.phone.label}${r.app ? `, ${r.app}` : ""}`, when]
  if (r.from || r.to) lines.push(participantsLine(r))
  if (r.body) lines.push(r.body)
  for (const f of r.fields ?? []) lines.push(`${f.label}: ${f.value}`)
  if (mark) lines.push(`[${mark}]`)
  lines.push(`Record ${r.id}`)
  return lines.join("\n")
}

export function usedInWords(u: PhoneRecordView["usedIn"]): string {
  if (!u) return "Not used in this case yet."
  const parts: string[] = []
  const add = (n: number, one: string, many: string) => n > 0 && parts.push(`${n} ${n === 1 ? one : many}`)
  add(u.findings, "finding", "findings")
  add(u.dossiers, "dossier", "dossiers")
  add(u.notes, "note", "notes")
  add(u.timeline, "Timeline entry", "Timeline entries")
  add(u.labels, "label", "labels")
  return parts.length ? `In ${parts.join(", ")}.` : "Not used in this case yet."
}
