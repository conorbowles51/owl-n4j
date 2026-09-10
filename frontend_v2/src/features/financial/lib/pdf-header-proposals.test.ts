import { expect, it } from "vitest"
import { proposePdfHeaders } from "./pdf-header-proposals"
const row = (row_index: number, text: string, column_index = 0) => ({
  row_index,
  cells: [{ column_index, expected_text: text }],
})
it("keeps exact original text and source positions while suggesting specific date roles", () => {
  const result = proposePdfHeaders([
    row(5, " Transaction\nDate "),
    row(6, "Value Date", 1),
  ])
  expect(result.proposals).toEqual([
    {
      row: 5,
      column: 0,
      text: " Transaction\nDate ",
      meaning: "transaction_date",
      label: "Transaction date",
    },
    {
      row: 6,
      column: 1,
      text: "Value Date",
      meaning: "value_date",
      label: "Value date",
    },
  ])
})
it("does not guess OCR repairs, substrings or financial context", () => {
  expect(
    proposePdfHeaders(
      [
        "Oate",
        "Opening Balance",
        "Total Amount",
        "Paid to creditor",
        "01/02",
        "constructor",
      ].map((v, i) => row(i, v))
    ).proposals
  ).toEqual([])
})
it("retains conflicting meanings without choosing and deduplicates repeated labels", () => {
  const result = proposePdfHeaders([
    row(0, "Debit"),
    row(1, "Credit"),
    row(2, "Debit"),
  ])
  expect(result.proposals.map((p) => p.meaning)).toEqual(["debit", "credit"])
})
it("reports the ten-row search limit without interpreting later content", () => {
  const result = proposePdfHeaders([
    ...Array.from({ length: 10 }, (_, i) => row(i, "")),
    row(10, "Amount"),
  ])
  expect(result).toEqual({ proposals: [], checkedRows: 10, hasMore: true })
})

it("retains generic date meaning without choosing a booking or transaction role", () => {
  expect(proposePdfHeaders([row(0, "Date")]).proposals[0].meaning).toBe("date")
})
