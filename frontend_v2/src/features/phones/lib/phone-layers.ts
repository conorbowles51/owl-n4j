/**
 * Phone layers: every phone in a case is its own layer, on or off. The choice is the screen's `phones` address
 * parameter (the scope's, so it carries between screens and survives a reload). An empty list means every phone;
 * a list names the phones that are on. The last phone on cannot be switched off: nothing on would read as "all".
 */

/** The `phone_layers` setting. Neil approved it on 18 Nov 2026 and the live build sets VITE_PHONE_LAYERS=on. A build
 * without it is off; there a person can see it with `?phone_layers=on` in the address (kept in this browser) or
 * `=off` to clear it. */
export function phoneLayersEnabled(): boolean {
  try {
    const q = new URLSearchParams(window.location.search).get("phone_layers")
    if (q === "on") localStorage.setItem("loupe.phone_layers", "on")
    if (q === "off") localStorage.removeItem("loupe.phone_layers")
    return import.meta.env.VITE_PHONE_LAYERS === "on" || localStorage.getItem("loupe.phone_layers") === "on"
  } catch {
    return import.meta.env.VITE_PHONE_LAYERS === "on"
  }
}

/** The phones that are on, in the case's order. */
export function layersOn(all: string[], chosen: string[]): string[] {
  if (!chosen.length) return all
  const set = new Set(chosen)
  const on = all.filter((id) => set.has(id))
  return on.length ? on : all
}

/** Stored form of a set of phones that are on: every phone on is the empty list. */
export function toChosen(all: string[], on: string[]): string[] {
  const set = new Set(on)
  const kept = all.filter((id) => set.has(id))
  return kept.length === all.length || kept.length === 0 ? [] : kept
}

export function toggleLayer(all: string[], chosen: string[], id: string): string[] {
  const on = layersOn(all, chosen)
  if (on.includes(id)) return on.length === 1 ? toChosen(all, on) : toChosen(all, on.filter((x) => x !== id))
  return toChosen(all, [...on, id])
}

export const onlyLayer = (all: string[], id: string): string[] => toChosen(all, [id])

/** Above this many phones the control adds a search box and groups the phones by owner. */
export const MANY_PHONES = 6

export interface OwnerGroup<T> { owner: string | null; phones: T[] }

/** Phones matching `query` (label or owner, any case) grouped by owner name: owners in name order, phones with no
 * owner named last, phones in the case's order inside each group. */
export function groupByOwner<T extends { label: string; owner?: string | null }>(phones: T[], query = ""): OwnerGroup<T>[] {
  const q = query.trim().toLowerCase()
  const kept = q ? phones.filter((p) => p.label.toLowerCase().includes(q) || (p.owner ?? "").toLowerCase().includes(q)) : phones
  const groups = new Map<string, OwnerGroup<T>>()
  for (const p of kept) {
    const key = p.owner?.trim() || ""
    if (!groups.has(key)) groups.set(key, { owner: key || null, phones: [] })
    groups.get(key)!.phones.push(p)
  }
  return [...groups.values()].sort((a, b) => (a.owner === null ? 1 : b.owner === null ? -1 : a.owner.localeCompare(b.owner)))
}
