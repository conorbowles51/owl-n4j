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
it("keeps right-aligned scanned amounts under their measured credit, debit and balance columns", () => {
  const header = row("header", 0, [
    cell(0, "Date", 31000, 49000),
    cell(1, "Description", 113000, 157000),
    cell(2, "Credit", 391000, 415000),
    cell(3, "Debit", 465000, 485000),
    cell(4, "Balance", 537000, 569000),
  ])
  const incoming = {
    ...row(
      "in",
      1,
      [
        cell(0, "2020-07-02", 31000, 76000),
        cell(1, "Incoming payment", 113000, 222000),
        cell(2, "900.00", 424000, 452000),
        cell(3, "1120.00", 566000, 598000),
      ],
      "transaction"
    ),
    fields: {
      date_column: "0",
      description_column: "1",
      credit_column: "2",
      balance_column: "3",
    },
  }
  const outgoing = {
    ...row(
      "out",
      2,
      [
        cell(0, "2020-07-03", 31000, 76000),
        cell(1, "Outgoing payment", 113000, 228000),
        cell(2, "300.00", 497000, 525000),
        cell(3, "820.00", 570000, 598000),
      ],
      "transaction"
    ),
    fields: {
      date_column: "0",
      description_column: "1",
      debit_column: "2",
      balance_column: "3",
    },
  }
  const opening = {
    ...row(
      "opening",
      3,
      [
        cell(0, "2020-07-01", 31000, 76000),
        cell(1, "Opening Balance", 113000, 181000),
        cell(2, "220.00", 570000, 598000),
      ],
      "balance"
    ),
    fields: { date_column: "0", description_column: "1", balance_column: "2" },
  }
  const rows = [header, incoming, outgoing, opening]
  const original = structuredClone(rows)
  const result = printedStatementSections(rows)
  expect(
    result.sections[0].rows.map((r) => r.cells.map((c) => c?.expected_text))
  ).toEqual([
    ["2020-07-02", "Incoming payment", "900.00", undefined, "1120.00"],
    ["2020-07-03", "Outgoing payment", undefined, "300.00", "820.00"],
    ["2020-07-01", "Opening Balance", undefined, undefined, "220.00"],
  ])
  expect(result.remaining).toEqual([])
  expect(rows).toEqual(original)
})
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

it("shows an amount wider than its left-aligned header without pulling in the adjacent column", () => {
  const payment = cell(2, "- $180.00", 520320, 561840)
  const unrelated = cell(3, "$25.00", 590000, 620000)
  const result = printedStatementSections([
    row("headers", 0, [
      cell(0, "Date", 25680, 46320),
      cell(1, "Description", 120720, 174240),
      cell(2, "Amount", 520320, 557520),
    ]),
    row(
      "payment",
      1,
      [
        cell(0, "May 30", 25680, 57360),
        cell(1, "CARD PAYMENT", 120480, 199200),
        payment,
        unrelated,
      ],
      "transaction"
    ),
  ])
  expect(result.sections[0].rows[0].cells[2]).toBe(payment)
  expect(result.remaining.flatMap((r) => r.source_cells)).toEqual([unrelated])
})

it("preserves Merrick's blank reference header, split description and separate payment minus", () => {
  const reference = cell(1, "7412061 3P00XTMJGS", 180000, 245000)
  const description = cell(2, "MOBILE PAYMENT-THANK YOU", 270000, 380000)
  const place = cell(3, "EXAMPLE CITY", 390000, 445000)
  const amount = cell(4, "114.00", 480000, 500000)
  const minus = cell(5, "-", 506000, 508000)
  const values = [
    cell(0, "O4/22", 90000, 110000),
    reference,
    description,
    place,
    amount,
    minus,
  ]
  const result = printedStatementSections([
    row("head", 0, [
      cell(0, "Trans Date", 90000, 120000),
      cell(1, "Item Description", 270000, 340000),
      cell(2, "Amount", 480000, 502000),
    ]),
    row("payment", 1, values, "unresolved"),
  ])
  expect(
    result.sections[0].columns.map((c) => c.header?.expected_text ?? "")
  ).toEqual(["Trans Date", "", "Item Description", "Amount"])
  expect(result.sections[0].rows[0].parts).toEqual([
    [values[0]],
    [reference],
    [description, place],
    [amount, minus],
  ])
  expect(result.remaining).toEqual([])
  expect(result.sections[0].rows[0].parts?.flat()).toEqual(values)
})

it("never joins two money values or cells on different lines into one displayed value", () => {
  const first = cell(2, "$14.00", 480000, 500000)
  const second = cell(3, "$15.00", 501000, 520000)
  const lower = cell(4, "LOWER LINE", 350000, 420000)
  lower.locator.rect = [350000, 20000, 420000, 28000]
  const result = printedStatementSections([
    row("head", 0, [
      cell(0, "Date", 90000, 120000),
      cell(1, "Description", 270000, 340000),
      cell(2, "Amount", 480000, 520000),
    ]),
    row(
      "payment",
      1,
      [
        cell(0, "Apr 22", 90000, 115000),
        cell(1, "SHOP", 270000, 300000),
        first,
        second,
        lower,
      ],
      "transaction"
    ),
  ])
  expect(result.sections[0].rows[0].parts?.[2]).toEqual([first])
  expect(result.remaining[0].source_cells).toEqual([second, lower])
})

it("keeps a damaged numeric date under Date and year-to-date notices outside the transaction grid", () => {
  const values = [
    cell(0, "0422", 90000, 115000),
    cell(1, "SHOP", 270000, 300000),
    cell(2, "14.00", 480000, 500000),
  ]
  const annual = row("annual", 2, [
    cell(0, "2021 Totals Year-to-Date", 90000, 220000),
  ])
  const footer = row("footer", 3, [
    cell(0, "Contact the bank for assistance.", 90000, 240000),
  ])
  const result = printedStatementSections([
    row("head", 0, [
      cell(0, "Trans Date", 90000, 120000),
      cell(1, "Item Description", 270000, 340000),
      cell(2, "Amount", 480000, 502000),
    ]),
    row("payment", 1, values, "unresolved"),
    annual,
    footer,
  ])
  expect(result.sections).toHaveLength(1)
  expect(result.sections[0].rows).toHaveLength(1)
  expect(result.sections[0].rows[0].parts).toEqual(values.map((c) => [c]))
  expect(result.remaining.flatMap((r) => r.source_cells)).toEqual([
    ...annual.source_cells,
    ...footer.source_cells,
  ])
})
