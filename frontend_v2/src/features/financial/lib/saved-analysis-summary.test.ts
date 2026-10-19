import { expect, it } from "vitest"
import { savedAnalysisSummary } from "./saved-analysis-summary"
it("shows the saved transfer amounts exactly and distinguishes source selection from totals", () => {
  const lines = savedAnalysisSummary({
    kind: "transfer-comparison",
    details: {
      basis: "Matching statement references",
      start_date: null,
      end_date: null,
      figures: [
        {
          currency: "EUR",
          posting_rows: 5,
          movement_count: 4,
          paired_transfers: 1,
          paired_amount_minor: "9007199254740993",
          unpaired_credits_minor: "500",
          unpaired_debits_minor: "300",
        },
      ],
    },
  })
  expect(lines.join(" ")).toContain("90,071,992,547,409.93 EUR")
  expect(lines.join(" ")).toContain("5 payments counted as 4 movements")
  expect(lines.join(" ")).toContain(
    "unpaired payments may be outside that selection"
  )
  expect(lines.join(" ")).toContain("Matching statement references")
})
it("does not manufacture figures for incomplete or other saved analysis", () => {
  expect(
    savedAnalysisSummary({ kind: "transfer-comparison", details: {} })
  ).toEqual([])
  expect(savedAnalysisSummary({ kind: "case-events" })).toEqual([])
})
