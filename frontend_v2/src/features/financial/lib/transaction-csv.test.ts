import { expect, it } from "vitest"
import { csvCell, parseNotesCsv, transactionCsv } from "./transaction-csv"
import { paymentFixture } from "./payment-fixture.test-support"
it("reads commas, newlines, escaped quotes and a BOM without losing note text", () => {
  expect(
    parseNotesCsv(
      '\uFEFFref_id,notes\r\nTX-1,"Ask ""why"", then\ncheck the source"\r\n'
    )
  ).toEqual([{ refId: "TX-1", notes: 'Ask "why", then\ncheck the source' }])
  expect(() => parseNotesCsv('ref,notes\nTX-1,"broken')).toThrow("not closed")
  expect(() => parseNotesCsv("ref,notes\nTX-1,")).toThrow("Row 2")
  expect(() => parseNotesCsv("name,notes\nTX-1,x")).toThrow("ref_id")
})
it("exports exact amounts, explicit currency and absent dates/balances with spreadsheet-safe text", () => {
  const text = transactionCsv([
    {
      ...paymentFixture,
      description: "=SUM(A1)",
      ordering_date_context: "statement_end_ordering_only",
      category: "Fees",
    },
  ])
  expect(text).toContain("90,071,992,547,409.93")
  expect(text).toContain('"EUR"')
  expect(text).toContain('"\'=SUM(A1)"')
  expect(text).not.toContain("2026-09-01")
  expect(csvCell("  @A1")).toBe('"\'  @A1"')
})
