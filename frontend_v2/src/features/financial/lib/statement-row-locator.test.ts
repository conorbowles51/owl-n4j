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

it("includes a wrapped amount and balance while retaining each field's source", () => {
  const row = {
    source_cells: [{ locator: locator(3, [100, 200, 700, 220]) }],
    value_sources: {
      amount: { source_cell: { locator: locator(3, [700, 224, 800, 244]) } },
      balance: { source_cell: { locator: locator(3, [850, 224, 950, 244]) } },
    },
  }
  const before = structuredClone(row)
  expect(statementRowLocator(row, 3)).toEqual(locator(3, [100, 200, 950, 244]))
  expect(row).toEqual(before)
  row.value_sources.balance.source_cell.locator.page_size = [1100, 2000]
  expect(statementRowLocator(row, 3)).toEqual({ kind: "page_only", page: 3 })
})
