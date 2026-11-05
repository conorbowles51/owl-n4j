export interface TextMark {
  start: number
  end: number
  kind: "match" | "current" | "passage"
}

export interface TextPiece {
  text: string
  kind: TextMark["kind"] | null
}

/** A page's text cut at its marks, so the pieces joined are the text exactly. A mark overlapping an earlier one is
 * cut to what is left of it; marks are offsets into this text in characters (code points), as the server counts. */
export function markedPieces(text: string, marks: TextMark[]): TextPiece[] {
  const characters = Array.from(text)
  const slice = (from: number, to?: number) => characters.slice(from, to).join("")
  const pieces: TextPiece[] = []
  let at = 0
  for (const mark of [...marks].sort((a, b) => a.start - b.start || b.end - a.end)) {
    const start = Math.max(at, mark.start)
    const end = Math.min(characters.length, mark.end)
    if (end <= start) continue
    if (start > at) pieces.push({ text: slice(at, start), kind: null })
    pieces.push({ text: slice(start, end), kind: mark.kind })
    at = end
  }
  if (at < characters.length || pieces.length === 0) pieces.push({ text: slice(at), kind: null })
  return pieces
}
