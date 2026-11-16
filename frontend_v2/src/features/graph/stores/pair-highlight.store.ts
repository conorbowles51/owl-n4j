import { create } from "zustand"
import { edgeKey } from "./edge-window.store"

/**
 * The phone pairs the Graph's "People in contact" panel points at (lx-graphclarity B4): the pair under the pointer
 * and the pairs chosen in the list. The canvas rings both people and draws the line between them in the highlight
 * colour, so the panel and the picture visibly belong together. Pairs are held as edgeKey(a, b) of identity keys.
 */
export interface PairHighlightState {
  hover: string | null
  chosen: string[]
  setHover: (key: string | null) => void
  setChosen: (keys: string[]) => void
}

export const usePairHighlight = create<PairHighlightState>()((set) => ({
  hover: null,
  chosen: [],
  setHover: (key) => set((s) => (s.hover === key ? s : { hover: key })),
  setChosen: (keys) => set({ chosen: keys }),
}))

const PREFIX = "phone-identity:"

/** The graph node keys and pair keys to highlight now. */
export function litPairs(hover: string | null, chosen: string[]): { nodes: Set<string>; links: Set<string> } {
  const links = new Set(hover ? [...chosen, hover] : chosen)
  const nodes = new Set<string>()
  for (const k of links) for (const side of k.split("|")) nodes.add(PREFIX + side)
  return { nodes, links }
}

/** True when a drawn link is one of the highlighted phone pairs. */
export function isLitLink(type: string, source: string, target: string, links: Set<string>): boolean {
  if (!links.size || type !== "COMMUNICATED" || !source.startsWith(PREFIX) || !target.startsWith(PREFIX)) return false
  return links.has(edgeKey(source.slice(PREFIX.length), target.slice(PREFIX.length)))
}
