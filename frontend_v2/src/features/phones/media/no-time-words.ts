import { fmt as n } from "../ui/count-sentence"

/**
 * The Media grid's sentence for files with no time. A file has no time when no message carried it, or when every
 * message that carried it has no time; the two are counted apart so neither is said of the other.
 */
export function noTimeWords(noTime: number, noMessage: number | undefined): string {
  if (!noTime) return ""
  if (noMessage === undefined) return ` ${n(noTime)} have no time; they are listed at the end.`
  const undated = noTime - noMessage
  const parts = [
    noMessage ? `${n(noMessage)} ${noMessage === 1 ? "was" : "were"} carried by no message` : "",
    undated ? `${n(undated)} ${undated === 1 ? "was" : "were"} carried only by messages with no time` : "",
  ].filter(Boolean)
  return ` ${parts.join(" and ")}; ${noTime === 1 ? "it has" : "they have"} no time and ${noTime === 1 ? "is" : "are"} listed at the end.`
}
