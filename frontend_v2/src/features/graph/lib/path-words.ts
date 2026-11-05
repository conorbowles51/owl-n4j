/** The stated limits of Shortest Paths (03 16.2): the search goes this many hops and has no limit per hop. */
export const PATH_MAX_HOPS = 10

const fmt = (n: number) => n.toLocaleString("en-US")

/** What came back: true counts, including the pairs with no path inside the limit. */
export function pathResultWords(paths: { length?: number }[], pairs: number, maxHops: number): string {
  const found = paths.length
  const lengths = paths.flatMap((p) => (typeof p.length === "number" ? [p.length] : []))
  const longest = lengths.length ? Math.max(...lengths) : null
  const parts = [`Found a path for ${fmt(found)} of ${fmt(pairs)} ${pairs === 1 ? "pair" : "pairs"}`]
  if (longest !== null) parts.push(`the longest is ${fmt(longest)} ${longest === 1 ? "hop" : "hops"}`)
  if (found < pairs) parts.push(`${fmt(pairs - found)} had no path within ${fmt(maxHops)} hops`)
  return `${parts.join("; ")}. Shown in spotlight.`
}
