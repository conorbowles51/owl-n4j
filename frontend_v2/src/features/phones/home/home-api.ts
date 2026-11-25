import { fetchAPI } from "@/lib/api-client"
import type { LensFilter, LensKind } from "@/features/timeline/lens/lens-api"

/**
 * The Phones page (screen 1 of the phones redesign): one list of every phone record in scope, narrowed by What, Who
 * and State. The counts come from POST /api/phones/home/facets (services/phone/phone_home.py), each exact and equal
 * to the list its value opens.
 */

export type CopiesOn = "one" | "many"
export type StateKey = "deleted" | CopiesOn

/** What: the screen's groups of the lens's kinds of record, in the design's order. Every kind is in one group. */
export const WHAT_GROUPS: { key: string; label: string; kinds: LensKind[] }[] = [
  { key: "comms", label: "Messages and calls", kinds: ["messages", "calls", "emails"] },
  { key: "places", label: "Places", kinds: ["locations"] },
  { key: "apps", label: "Apps and accounts", kinds: ["apps", "accounts"] },
  { key: "web", label: "Web and searches", kinds: ["web"] },
  { key: "media", label: "Files and media", kinds: ["media"] },
  { key: "device", label: "Device events", kinds: ["device", "sensor"] },
  { key: "other", label: "Everything else", kinds: ["other"] },
]
export const ALL_GROUP = { key: "all", label: "Everything", kinds: WHAT_GROUPS.flatMap((g) => g.kinds) }
export const DEFAULT_WHAT = "comms"

export function whatGroup(key: string | null) {
  return key === "all" ? ALL_GROUP : WHAT_GROUPS.find((g) => g.key === key) ?? WHAT_GROUPS[0]
}

export interface HomeFacets {
  case_id: string
  kinds?: { key: LensKind; label: string; count: number; on: boolean }[]
  people?: { key: string; label: string; count: number; phones: string[]; on: boolean }[]
  people_total?: number
  people_applies?: boolean
  states?: { key: StateKey; label: string; count: number; on: boolean; applies?: boolean }[]
  states_note?: string
  phones?: { extraction_id: string; first_day: string; last_day: string }[]
}

export type FacetPart = "kinds" | "people" | "states" | "phones"

export async function homeFacets(filter: LensFilter & { copies_on?: CopiesOn }, part: FacetPart): Promise<HomeFacets> {
  return fetchAPI<HomeFacets>(`/api/phones/home/facets?part=${part}`, { method: "POST", body: filter, read: true })
}

/** A group's count is the sum of its kinds' counts (each record has one kind). */
export function groupCount(kinds: HomeFacets["kinds"], keys: LensKind[]): number | null {
  if (!kinds) return null
  return kinds.filter((k) => keys.includes(k.key)).reduce((n, k) => n + k.count, 0)
}

/** Weeks picked on the activity strip, as the scope's from/to days (the week's Monday to its Sunday). */
export function weeksToWindow(walls: string[], a: number, b: number): { from: string; to: string } {
  const [lo, hi] = a <= b ? [a, b] : [b, a]
  const from = walls[lo].slice(0, 10)
  const end = new Date(`${walls[hi].slice(0, 10)}T00:00:00Z`)
  end.setUTCDate(end.getUTCDate() + 6)
  return { from, to: end.toISOString().slice(0, 10) }
}

/** The weeks inside a window, for drawing the picked weeks. */
export function weekInWindow(wall: string, window: { from: string; to: string } | null): boolean {
  if (!window) return false
  const d = wall.slice(0, 10)
  const end = new Date(`${d}T00:00:00Z`)
  end.setUTCDate(end.getUTCDate() + 6)
  return end.toISOString().slice(0, 10) >= window.from && d <= window.to
}
