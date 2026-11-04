import type { ResultCountProps } from "./ResultCount"

// One formatter for every call: n.toLocaleString("en-US") builds a new formatter each time (208 ms of main-thread
// time on the P12 record page, lx-mainthread); Intl.NumberFormat("en-US").format gives the same text by spec.
const EN_US = new Intl.NumberFormat("en-US")
export const fmt = (n: number) => EN_US.format(n)

export function countSentence({ shown, total, noun, singular, soFar }: Pick<ResultCountProps, "shown" | "total" | "noun" | "singular" | "soFar">): string {
  const word = total === 1 ? (singular ?? noun.replace(/s$/, "")) : noun
  const tail = soFar ? " (so far)" : ""
  if (shown >= total) return `${fmt(total)} ${word}${tail}`
  return `Showing ${fmt(shown)} of ${fmt(total)} ${word}${tail}`
}
