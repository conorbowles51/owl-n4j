import { expect, it } from "vitest"
import { proposeStatementControls } from "./statement-control-proposals"
const row = (row_index: number, ...texts: string[]) => ({
  row_index,
  cells: texts.map((expected_text, column_index) => ({
    column_index,
    expected_text,
    locator: { row: row_index, column: column_index },
  })),
})
it("preserves repeated labels and all same-row numeric candidates without parsing", () => {
  const rows = [
    row(0, "Previous Balance:", "$1,234.00", "$5.00"),
    row(1, "Previous Balance", "$3.00"),
  ]
  const result = proposeStatementControls(rows, "opening balance")
  expect(result.map((p) => p.values.map((v) => v.expected_text))).toEqual([
    ["$1,234.00", "$5.00"],
    ["$3.00"],
  ])
  expect(result[0].values[0]).toBe(rows[0].cells[1])
})
it("does not mistake subtotals, due dates, nearby rows or conflicting labels for controls", () => {
  expect(
    proposeStatementControls(
      [
        row(0, "Total Purchases", "$10.00"),
        row(1, "Interest Charged", "$5.00"),
      ],
      "total money out"
    )
  ).toEqual([])
  expect(
    proposeStatementControls(
      [row(0, "Payment Due Date", "2026-01-01")],
      "statement end"
    )
  ).toEqual([])
  expect(
    proposeStatementControls(
      [
        row(0, "Opening Balance"),
        row(1, "$100.00"),
        row(2, "Opening Balance", "Previous Balance", "$2.00"),
      ],
      "opening balance"
    )
  ).toEqual([])
})

it("does not cross intervening headings on a multi-panel statement", () => {
  const source = [
    row(0, "New Balance", "Minimum Payment Due", "Other Credits", "$0.00"),
    row(1, "New Balance", "= $6,637.96"),
  ]
  const result = proposeStatementControls(source, "closing balance")
  expect(result).toHaveLength(1)
  expect(result[0].row).toBe(1)
  expect(result[0].values[0].expected_text).toBe("= $6,637.96")
})
