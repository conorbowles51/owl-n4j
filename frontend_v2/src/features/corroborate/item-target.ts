/**
 * Any item can name itself for Corroborate with two attributes: data-corro="<type>:<id>" and an optional
 * data-corro-label. Right-click and the key C (lx-corroselect C) read them from the item under the pointer or focus.
 */
import type { RelationMember } from "@/features/relations/api"

export function corroAttrs(type: string, id: string, label?: string, extra?: { quote?: string; also?: { type: string; id: string }[] }): Record<string, string> {
  return {
    "data-corro": `${type}:${id}`,
    ...(label ? { "data-corro-label": label.slice(0, 300) } : {}),
    // A marked passage: the document is the member, the words are kept with it (never reworded).
    ...(extra?.quote ? { "data-corro-quote": extra.quote.slice(0, 2000) } : {}),
    // An item that is two things at once, like a graph link: its other end, as "type:id" separated by spaces.
    ...(extra?.also?.length ? { "data-corro-also": extra.also.map((a) => `${a.type}:${a.id}`).join(" ") } : {}),
  }
}

function split(raw: string): { type: string; id: string } | null {
  const at = raw.indexOf(":")
  return at <= 0 || at === raw.length - 1 ? null : { type: raw.slice(0, at), id: raw.slice(at + 1) }
}

/** Every member the item under the pointer stands for: itself, then any data-corro-also ends (a graph link's two entities). */
export function membersFromElement(el: Element | null): RelationMember[] {
  const first = memberFromElement(el)
  if (!first) return []
  const host = el?.closest?.("[data-corro]")
  const also = (host?.getAttribute("data-corro-also") ?? "").split(" ").map(split).filter((m): m is { type: string; id: string } => !!m)
  return [first, ...also.filter((m) => !(m.type === first.type && m.id === first.id))]
}

export function memberFromElement(el: Element | null): RelationMember | null {
  const host = el?.closest?.("[data-corro]")
  const raw = host?.getAttribute("data-corro")
  if (!host || !raw) return null
  const at = raw.indexOf(":")
  if (at <= 0 || at === raw.length - 1) return null
  const label = host.getAttribute("data-corro-label")
  const quote = host.getAttribute("data-corro-quote")
  return { type: raw.slice(0, at), id: raw.slice(at + 1), ...(label ? { label } : {}), ...(quote ? { quote } : {}) }
}

/** True when the key press belongs to a text field, so C is typed there and never starts a Corroborate. */
export function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable === true
}
