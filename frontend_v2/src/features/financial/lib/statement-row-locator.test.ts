import { expect, it } from "vitest"
import { statementRowLocator } from "./statement-row-locator"
const locator = (page: number, rect: number[]) => ({
  kind: "page_rectangle",
  page,
  rect,
  page_size: [1000, 2000],
  units: "millipoints",
  space: "pdf_displayed",
})
it("combines measured cells on one page and does not change source locations", () => {
  const cells = [
    locator(3, [100, 200, 400, 220]),
    locator(3, [700, 200, 800, 220]),
    locator(4, [0, 0, 999, 999]),
  ]
  expect(
    statementRowLocator(
      { source_cells: cells.map((locator) => ({ locator })) },
      3
    )
  ).toEqual(locator(3, [100, 200, 800, 220]))
  expect(cells[0].rect).toEqual([100, 200, 400, 220])
  expect(
    statementRowLocator({ source_cells: [{ locator: { bad: "data" } }] }, 3)
  ).toEqual({ kind: "page_only", page: 3 })
})
