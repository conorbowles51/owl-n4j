import type { ThreadTranslateCounts } from "../api"

const n = (v: number) => v.toLocaleString("en-US")
const msgs = (v: number) => `${n(v)} ${v === 1 ? "message" : "messages"}`

/** "Translate this conversation" in words (05 17.5): how many were queued and every one left out, by reason. */
export function translateWords(c: ThreadTranslateCounts): string {
  const head = c.queued
    ? `${msgs(c.queued)} of ${n(c.in_conversation)} queued for translation on this server; nothing is sent anywhere.`
    : `Nothing new to translate in this conversation of ${msgs(c.in_conversation)}.`
  const out = [
    c.left_out.already_translated ? `${n(c.left_out.already_translated)} already translated` : null,
    c.left_out.already_waiting ? `${n(c.left_out.already_waiting)} already waiting` : null,
    c.left_out.no_text ? `${n(c.left_out.no_text)} with no text` : null,
  ].filter(Boolean)
  return out.length ? `${head} Left out: ${out.join(", ")}.` : head
}
