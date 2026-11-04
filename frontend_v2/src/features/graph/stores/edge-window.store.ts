import { create } from "zustand"

/**
 * The Graph time slider's window for communication edges (03 section 14.3): while a window is set, each phone
 * identity pair's count for that window is held here and the canvas restyles its edge from it (width by count, a
 * faint dashed line where the pair has none in the window) without reloading any node.
 */
export interface EdgeWindowState {
  window: { from: string; to: string } | null
  counts: Record<string, number>
  setWindow: (w: { from: string; to: string } | null) => void
  setCount: (key: string, n: number) => void
}

export const edgeKey = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`)

export const useEdgeWindow = create<EdgeWindowState>()((set) => ({
  window: null,
  counts: {},
  setWindow: (w) => set({ window: w, counts: {} }),
  setCount: (key, n) => set((s) => (s.counts[key] === n ? s : { counts: { ...s.counts, [key]: n } })),
}))

const PREFIX = "phone-identity:"

/** How the canvas draws one link under the window: null leaves it as it is (no window, or not a phone pair, or not
 * counted yet). */
export function windowStyle(type: string, source: string, target: string, w: EdgeWindowState["window"], counts: Record<string, number>):
  { widthFactor: number; alpha: number; dashed: boolean } | null {
  if (!w || type !== "COMMUNICATED" || !source.startsWith(PREFIX) || !target.startsWith(PREFIX)) return null
  const n = counts[edgeKey(source.slice(PREFIX.length), target.slice(PREFIX.length))]
  if (n === undefined) return null
  if (n === 0) return { widthFactor: 0.5, alpha: 0.12, dashed: true }
  return { widthFactor: 1 + Math.log10(n + 1), alpha: 0.7, dashed: false }
}
