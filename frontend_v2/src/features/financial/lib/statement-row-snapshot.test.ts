import { expect, it } from "vitest"
import {
  statementReviewSnapshot,
  statementRowSnapshot,
} from "./statement-row-snapshot"
import {
  serverStatementDraft,
  type StatementDraft,
} from "./statement-review-draft"

const row: StatementDraft["rows"][number] = {
  id: "row",
  excluded: false,
  date: "2026-01-05",
  description: "Synthetic payment",
  counterparty: "",
  amount_minor: "15781",
  direction: "debit",
  balance_minor: "84219",
  reason: "",
}
it("recognizes an acknowledged row despite omitted optional fields and object ordering", () => {
  const restored = serverStatementDraft({
    expected_revision: "synthetic",
    rows: [
      {
        ...Object.fromEntries(Object.entries(row).reverse()),
        manual_page: null,
        source_order_anchor: null,
        date_values: {},
      },
    ],
  })!
  expect(statementRowSnapshot(restored.rows[0])).toBe(statementRowSnapshot(row))
})
it("a saved balance cannot mark newer payment, date, link or note edits as saved", () => {
  for (const change of [
    { description: "Later edit" },
    { amount_minor: "15782" },
    { date: "2026-01-06" },
    { reason: "Later note" },
    { counterparty_link: { kind: "party" as const, id: "new-party" } },
  ]) {
    expect(statementRowSnapshot({ ...row, ...change })).not.toBe(
      statementRowSnapshot(row)
    )
  }
})
it("acknowledges API defaults and key order without accepting changed review values", () => {
  const request = {
    expected_revision: "synthetic",
    currency: "EUR",
    holder: "Example",
    account_number: "00123",
    rows: [row],
  }
  const response = {
    ...Object.fromEntries(Object.entries(request).reverse()),
    replaces_source_document_id: null,
    replacement_revision: null,
    institution: "",
    period_start: "",
    no_activity_confirmed: false,
    rows: [
      {
        ...row,
        manual_page: null,
        source_order_anchor: null,
        counterparty_link: null,
        date_values: {},
        date_unprinted: false,
      },
    ],
  }
  expect(statementReviewSnapshot(response)).toBe(
    statementReviewSnapshot(request)
  )
  for (const change of [
    { currency: "USD" },
    { holder: "Other" },
    { account_number: "00124" },
    { rows: [{ ...row, balance_minor: "50025" }] },
  ])
    expect(statementReviewSnapshot({ ...response, ...change })).not.toBe(
      statementReviewSnapshot(request)
    )
})
