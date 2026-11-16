/**
 * Phone layers: every phone in a case is its own layer, on or off. The choice is the screen's `phones` address
 * parameter (the scope's, so it carries between screens and survives a reload). An empty list means every phone;
 * a list names the phones that are on. The last phone on cannot be switched off: nothing on would read as "all".
 */

/** The `phone_layers` setting. Off until Neil approves the mock-up; a build sets VITE_PHONE_LAYERS=on, and a person
 * can see it ahead of that with `?phone_layers=on` in the address (kept in this browser) or `=off` to clear it. */
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
