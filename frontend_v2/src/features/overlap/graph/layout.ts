export const W = 640
export const H = 520

/** Places each person on a circle, the busiest at the top. */
export function layout(keys: string[]): Map<string, { x: number; y: number }> {
  const out = new Map<string, { x: number; y: number }>()
  const r = Math.min(W, H) / 2 - 70
  keys.forEach((k, i) => {
    const t = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(1, keys.length)
    out.set(k, { x: W / 2 + r * Math.cos(t), y: H / 2 + r * Math.sin(t) })
  })
  return out
}

/** Line width from the records between two people: wider for more, never wider than 12 px. */
export function lineWidth(records: number, most: number) {
  return 1 + 11 * Math.sqrt(records / Math.max(1, most))
}

