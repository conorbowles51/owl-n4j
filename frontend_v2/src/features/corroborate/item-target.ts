/**
 * Any item can name itself for Corroborate with two attributes: data-corro="<type>:<id>" and an optional
 * data-corro-label. Right-click and the key C (lx-corroselect C) read them from the item under the pointer or focus.
 */
import type { RelationMember } from "@/features/relations/api"

export function corroAttrs(type: string, id: string, label?: string): Record<string, string> {
  return { "data-corro": `${type}:${id}`, ...(label ? { "data-corro-label": label } : {}) }
}

export function memberFromElement(el: Element | null): RelationMember | null {
  const host = el?.closest?.("[data-corro]")
  const raw = host?.getAttribute("data-corro")
  if (!host || !raw) return null
  const at = raw.indexOf(":")
  if (at <= 0 || at === raw.length - 1) return null
  const label = host.getAttribute("data-corro-label")
  return { type: raw.slice(0, at), id: raw.slice(at + 1), ...(label ? { label } : {}) }
}

/** True when the key press belongs to a text field, so C is typed there and never starts a Corroborate. */
export function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable === true
}
