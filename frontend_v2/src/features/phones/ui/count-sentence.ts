import type { ResultCountProps } from "./ResultCount"

export const fmt = (n: number) => n.toLocaleString("en-US")

export function countSentence({ shown, total, noun, singular, soFar }: Pick<ResultCountProps, "shown" | "total" | "noun" | "singular" | "soFar">): string {
  const word = total === 1 ? (singular ?? noun.replace(/s$/, "")) : noun
  const tail = soFar ? " (so far)" : ""
  if (shown >= total) return `${fmt(total)} ${word}${tail}`
  return `Showing ${fmt(shown)} of ${fmt(total)} ${word}${tail}`
}
