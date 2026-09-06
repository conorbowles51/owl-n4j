/** Map textarea UTF-16 offsets back to canonical Unicode code points.
 * Textareas normalize CRLF and CR to LF; canonical source text is unchanged.
 */
export function sourceSelection(content: string, start: number, end: number) {
  const points = Array.from(content)
  const boundaries = new Map<number, number>([[0, 0]])
  let displayOffset = 0
  for (let i = 0; i < points.length; i++) {
    if (points[i] === "\r" && points[i + 1] === "\n") i++
    displayOffset += points[i].length
    boundaries.set(displayOffset, i + 1)
  }
  const left = boundaries.get(start)
  const right = boundaries.get(end)
  if (
    left === undefined ||
    right === undefined ||
    right <= left ||
    right - left > 128
  )
    return null
  return { start: left, end: right, text: points.slice(left, right).join("") }
}
