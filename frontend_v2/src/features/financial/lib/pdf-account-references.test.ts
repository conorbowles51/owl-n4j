import { expect, it } from "vitest"
import { proposePdfAccountReferences } from "./pdf-account-references"
const row = (text: string, index = 0) => ({
  row_index: index,
  cells: [
    {
      column_index: 0,
      expected_text: text,
      locator: { page: 1, rect: [1, 2, 3, 4] },
    },
  ],
})
it("retains exact inline and adjacent-cell references and their source locations", () => {
  const rows = [
    row("Platinum MasterCard Account Ending in 1234"),
    {
      row_index: 1,
      cells: [
        { column_index: 2, expected_text: "Account Number:", locator: {} },
        {
          column_index: 3,
          expected_text: "1111 2222 3333 4444",
          locator: { page: 1 },
        },
      ],
    },
  ]
  const result = proposePdfAccountReferences(rows)
  expect(
    result.references.map((r) => [r.reference, r.partial, r.row, r.column])
  ).toEqual([
    ["1234", true, 0, 0],
    ["1111 2222 3333 4444", false, 1, 3],
  ])
  expect(result.references[0].locator).toEqual(rows[0].cells[0].locator)
  expect(result.distinctReferences).toBe(2)
})
it("keeps masked values partial and refuses amounts, vague labels and unsupported OCR characters", () => {
  expect(
    proposePdfAccountReferences([row("Account number: XXXX-1234")])
      .references[0].partial
  ).toBe(true)
  for (const text of [
    "Balance: 1234",
    "Account: 1234",
    "Account Number: 12O4",
    "Account number: 123.45",
    "Account number: 1234 due",
  ])
    expect(proposePdfAccountReferences([row(text)]).references).toEqual([])
})
it("does not jump over intervening cells or hide its bounded search", () => {
  const distant = {
    row_index: 0,
    cells: [
      { column_index: 0, expected_text: "Account number", locator: {} },
      { column_index: 2, expected_text: "12345678", locator: {} },
    ],
  }
  expect(proposePdfAccountReferences([distant]).references).toEqual([])
  const result = proposePdfAccountReferences([
    ...Array.from({ length: 30 }, (_, i) => row("Other text", i)),
    row("Account number: 12345678", 30),
  ])
  expect(result).toMatchObject({
    references: [],
    checkedRows: 30,
    hasMore: true,
    distinctReferences: 0,
  })
})
