/**
 * The selected characters of a text panel, as offsets into the panel's text. A plain DOM Range: it needs no clipboard
 * API and no secure context, so it works over http://, and the marks inside the panel do not change the count.
 * Offsets count characters (code points), as the server's stored text does; a browser string counts an emoji as two.
 */
export function selectionOffsets(container: Node, selection: Selection | null): { start: number; end: number } | null {
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null
  const range = selection.getRangeAt(0)
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) return null
  const before = document.createRange()
  before.selectNodeContents(container)
  before.setEnd(range.startContainer, range.startOffset)
  const start = Array.from(before.toString()).length
  const end = start + Array.from(range.toString()).length
  return end > start ? { start, end } : null
}
