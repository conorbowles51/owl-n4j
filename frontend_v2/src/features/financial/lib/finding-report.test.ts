import { expect, it } from "vitest"
import type { CaseworkEntry } from "@/features/workspace/casework-api"
import { findingReport } from "./finding-report"
import { paymentFixture } from "./payment-fixture.test-support"

function entry(overrides: Record<string, unknown> = {}) {
  return {
    id: "entry",
    case_id: "case",
    title: "Review <bank>",
    body: "Ask why & retain original",
    entry_type: "note",
    tags: ["financial"],
    review_state: "accepted",
    version: 1,
    migration_metadata: {},
    needs_migration_review: false,
    links: [
      {
        id: "link",
        entry_id: "entry",
        relationship: "context",
        case_id: "case",
        target_type: "evidence",
        target_id: "file",
        target_label: "source.pdf",
        source_anchor: { financial_transaction_ids: ["payment"] },
        metadata: {
          schema: "loupe.financial.payment_selection/1",
          transactions: [paymentFixture],
        },
      },
    ],
    ...overrides,
  } as CaseworkEntry
}
it("exports exactly the saved selection with escaped user text and exact large amounts", () => {
  const html = findingReport(entry(), "case")
  expect(html).toContain("90,071,992,547,409.93")
  expect(html).toContain("&lt;script&gt;bad()&lt;/script&gt;")
  expect(html).not.toContain("<script>")
  expect(html).toContain("Selected payments (1)")
  expect(html).toContain("TX-123")
  expect(html).toContain(
    "Original statement files and unrelated case records are not included"
  )
})
it("refuses another case or a payment absent from its supporting link", () => {
  expect(() => findingReport(entry({ case_id: "other" }), "case")).toThrow(
    "another case"
  )
  const e = entry()
  e.links[0].source_anchor.financial_transaction_ids = []
  expect(() => findingReport(e, "case")).toThrow("supporting link")
})
it("exports an existing note without inventing a payment snapshot", () => {
  const e = entry()
  e.links[0].metadata = {}
  const html = findingReport(e, "case")
  expect(html).not.toContain("Selected payments")
  expect(html).toContain("source.pdf")
})
