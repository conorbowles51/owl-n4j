import { readLocator } from "./locator"

// The navigation highlight covers only measured cells on the same source page.
// It is a display aid; the individual stored field locations remain unchanged.
export function statementRowLocator(
  row: { source_cells: { locator: unknown }[] } | undefined,
  page: number
) {
  const rectangles = (row?.source_cells ?? []).flatMap((cell) => {
    const reading = readLocator(cell.locator)
    return reading.ok &&
      reading.locator.kind === "page_rectangle" &&
      reading.locator.page === page
      ? [reading.locator.rectangle]
      : []
  })
  const first = rectangles[0]
  if (
    !first ||
    rectangles.some(
      (rect) =>
        rect.pageWidth !== first.pageWidth ||
        rect.pageHeight !== first.pageHeight
    )
  )
    return { kind: "page_only", page }
  return {
    kind: "page_rectangle",
    page,
    rect: [
      Math.min(...rectangles.map((r) => r.x0)),
      Math.min(...rectangles.map((r) => r.y0)),
      Math.max(...rectangles.map((r) => r.x1)),
      Math.max(...rectangles.map((r) => r.y1)),
    ],
    page_size: [first.pageWidth, first.pageHeight],
    units: "millipoints",
    space: "pdf_displayed",
  }
}
