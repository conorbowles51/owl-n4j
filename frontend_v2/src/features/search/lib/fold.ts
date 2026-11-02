import tables from "./fold-tables.json"

/**
 * The browser's copy of 02 section 8.4's fold (backend/services/phone/fold.py), for highlighting matches on screen.
 * Same steps, same order: NFKC; styled letters NFKC leaves alone; Cyrillic and Greek look-alikes inside a token that
 * mixes them with Latin; format and control characters removed (ZERO WIDTH SPACE becomes a space); combining marks
 * removed; case folded; anything not a letter, digit or mark to a space, whitespace collapsed. ``exact`` keeps only
 * the format-character and case steps. Both suites read backend/tests/fixtures/fold_cases.json (A8).
 */
const STYLED = new Map(Object.entries(tables.styled as Record<string, string>).map(([k, v]) => [String.fromCodePoint(parseInt(k, 16)), v]))
const CONFUSABLE = new Map(Object.entries(tables.confusable as Record<string, string>).map(([k, v]) => [String.fromCodePoint(parseInt(k, 16)), v]))

// Python's casefold beyond toLowerCase, for the letters that survive NFKC
const CASEFOLD: Record<string, string> = { "ß": "ss", "ς": "σ", "ẞ": "ss", "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st", "İ": "i̇" }

function script(ch: string): "latin" | "cyrillic" | "greek" | "other" | null {
  if (!/\p{L}/u.test(ch)) return null
  if (/\p{Script=Latin}/u.test(ch)) return "latin"
  if (/\p{Script=Cyrillic}/u.test(ch)) return "cyrillic"
  if (/\p{Script=Greek}/u.test(ch)) return "greek"
  return "other"
}

function confusables(text: string): string {
  return text
    .split(/(\s+)/u)
    .map((token) => {
      const scripts = new Set(Array.from(token, script))
      if (!(scripts.has("latin") && (scripts.has("cyrillic") || scripts.has("greek")))) return token
      return Array.from(token, (c) => {
        const s = script(c)
        return s === "cyrillic" || s === "greek" ? (CONFUSABLE.get(c) ?? c) : c
      }).join("")
    })
    .join("")
}

function stripFormat(text: string): string {
  return Array.from(text, (c) => (c === "​" ? " " : /[\p{Cf}\p{Cc}]/u.test(c) && !"\t\n\r".includes(c) ? "" : c)).join("")
}

function casefold(text: string): string {
  return Array.from(text.toLowerCase(), (c) => CASEFOLD[c] ?? c).join("")
}

export function fold(text: string | null | undefined, exact = false): string {
  if (!text) return ""
  if (exact) return casefold(stripFormat(text))
  let s = text.normalize("NFKC")
  s = Array.from(s, (c) => STYLED.get(c) ?? c).join("")
  s = confusables(s)
  s = stripFormat(s)
  s = s.normalize("NFD").replace(/\p{Mn}/gu, "").normalize("NFC")
  s = casefold(s)
  s = s.replace(/[^\p{L}\p{N}\p{M}]/gu, " ")
  return s.replace(/\s+/gu, " ").trim()
}
