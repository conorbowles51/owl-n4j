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

function stepsAfterStyle(s: string): string {
  s = stripFormat(s)
  s = s.normalize("NFD").replace(/\p{Mn}/gu, "").normalize("NFC")
  return casefold(s).replace(/[^\p{L}\p{N}\p{M}]/gu, " ")
}

/**
 * ``fold`` one character at a time, with the index in ``text`` that produced each folded character, as the
 * backend's ``fold_with_map`` does: a match at folded[a, b) is text.slice(starts[a], starts[b - 1] + length of
 * that character) in the original. Indexes are UTF-16 offsets, so they slice JavaScript strings directly.
 */
export function foldWithMap(text: string, exact = false): { folded: string; starts: number[]; ends: number[] } {
  const chars: { at: number; ch: string }[] = []
  for (let i = 0; i < text.length; ) {
    const cp = text.codePointAt(i)!
    const ch = String.fromCodePoint(cp)
    chars.push({ at: i, ch })
    i += ch.length
  }
  let pieces: string[]
  if (exact) pieces = chars.map(({ ch }) => casefold(stripFormat(ch)))
  else {
    const styled = chars.map(({ ch }) => Array.from(ch.normalize("NFKC"), (c) => STYLED.get(c) ?? c).join(""))
    for (let i = 0; i < styled.length; ) {
      if (!styled[i] || /^\s+$/u.test(styled[i])) {
        i++
        continue
      }
      let j = i
      while (j < styled.length && styled[j] && !/^\s+$/u.test(styled[j])) j++
      const scripts = new Set(styled.slice(i, j).flatMap((s) => Array.from(s, script)))
      if (scripts.has("latin") && (scripts.has("cyrillic") || scripts.has("greek")))
        for (let k = i; k < j; k++)
          styled[k] = Array.from(styled[k], (c) => {
            const s = script(c)
            return s === "cyrillic" || s === "greek" ? (CONFUSABLE.get(c) ?? c) : c
          }).join("")
      i = j
    }
    pieces = styled.map(stepsAfterStyle)
  }
  const out: string[] = []
  const starts: number[] = []
  const ends: number[] = []
  pieces.forEach((piece, n) => {
    for (let c of Array.from(piece)) {
      if (!exact && /\s/u.test(c)) {
        if (!out.length || out[out.length - 1] === " ") continue
        c = " "
      }
      for (let u = 0; u < c.length; u++) {
        out.push(u === 0 ? c : "")
        starts.push(chars[n].at)
        ends.push(chars[n].at + chars[n].ch.length)
      }
    }
  })
  // drop the empty placeholders of surrogate pairs so folded indexes match string indexes
  const folded: string[] = []
  const s2: number[] = []
  const e2: number[] = []
  out.forEach((c, k) => {
    if (c === "") return
    for (let u = 0; u < c.length; u++) {
      folded.push(c[u])
      s2.push(starts[k])
      e2.push(ends[k])
    }
  })
  while (!exact && folded.length && folded[folded.length - 1] === " ") {
    folded.pop()
    s2.pop()
    e2.pop()
  }
  return { folded: folded.join(""), starts: s2, ends: e2 }
}

/** Every match of ``query`` in ``text`` as original [start, end) ranges, folded the same way on both sides. */
export function matchRanges(text: string, query: string, exact = false): [number, number][] {
  const q = foldWithMap(query, exact).folded
  if (!q || !text) return []
  const { folded, starts, ends } = foldWithMap(text, exact)
  const out: [number, number][] = []
  for (let at = folded.indexOf(q); at >= 0; at = folded.indexOf(q, at + q.length)) out.push([starts[at], ends[at + q.length - 1]])
  return out
}
