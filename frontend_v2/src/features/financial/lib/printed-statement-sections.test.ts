import { expect, it } from "vitest"
import {
  printedStatementSections,
  type PrintedRow,
} from "./printed-statement-sections"
const cell = (
  column_index: number,
  expected_text: string,
  x: number,
  right: number
) => ({
  column_index,
  expected_text,
  locator: { kind: "page_rectangle", page: 3, rect: [x, 1000, right, 9000] },
})
const row = (
  id: string,
  row_index: number,
  source_cells: PrintedRow["source_cells"],
  kind = "statement_information"
) => ({ id, row_index, page_number: 3, table_index: 0, kind, source_cells })
it("separates printed cardholder sections, drops the adjacent ad from the table, and aligns the printed total by position", () => {
  const rows = [
    row("title", 0, [
      cell(0, "A PERSON #1234: Transactions", 40000, 280000),
      cell(1, "Mobile app advertisement", 410000, 580000),
    ]),
    row("header", 1, [
      cell(0, "Date", 40000, 60000),
      cell(1, "Description", 80000, 120000),
      cell(2, "Amount", 280000, 310000),
      cell(3, "Data rates may apply", 330000, 580000),
    ]),
    row(
      "payment",
      2,
      [
        cell(0, "Sep 20", 40000, 70000),
        cell(1, "SHOP", 80000, 140000),
        cell(2, "$28.78", 282000, 310000),
      ],
      "transaction"
    ),
    row("total", 3, [
      cell(0, "A PERSON #1234: Total", 40000, 190000),
      cell(1, "$28.78", 282000, 310000),
    ]),
    row("next-title", 4, [
      cell(0, "OTHER PERSON #5678: Transactions", 40000, 285000),
    ]),
    row("next-header", 5, [
      cell(0, "Date", 40000, 60000),
      cell(1, "Description", 80000, 120000),
      cell(2, "Amount", 280000, 310000),
    ]),
  ]
  const result = printedStatementSections(rows)
  expect(result.sections).toHaveLength(2)
  expect(result.sections[0].title?.expected_text).toBe(
    "A PERSON #1234: Transactions"
  )
  expect(result.sections[0].headers).toHaveLength(3)
  expect(result.sections[0].rows[1].cells.map((c) => c?.expected_text)).toEqual(
    ["A PERSON #1234: Total", undefined, "$28.78"]
  )
  expect(
    result.remaining.flatMap((r) => r.source_cells.map((c) => c.expected_text))
  ).toContain("Data rates may apply")
  expect(result.sections[1].title?.expected_text).toContain("OTHER PERSON")
  // Every nonblank source cell remains available, either in a section or in additional text.
  const visible = [
    ...result.sections.flatMap((s) => [
      s.title,
      ...s.headers,
      ...s.rows.flatMap((r) => r.cells),
    ]),
    ...result.remaining.flatMap((r) => r.source_cells),
  ].filter(Boolean)
  for (const c of rows.flatMap((r) => r.source_cells))
    expect(visible).toContain(c)
})
it("keeps a transaction immediately before a repeated header", () => {
  const headers = [
    cell(0, "Date", 40000, 60000),
    cell(1, "Description", 80000, 120000),
    cell(2, "Amount", 280000, 310000),
  ]
  const result = printedStatementSections([
    row("h1", 0, headers),
    row(
      "tx",
      1,
      [
        cell(0, "Sep 20", 40000, 70000),
        cell(1, "SHOP", 80000, 140000),
        cell(2, "$28.78", 282000, 310000),
      ],
      "transaction"
    ),
    row("h2", 2, headers),
  ])
  expect(result.sections[0].rows[0].row.id).toBe("tx")
})
