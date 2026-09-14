import { beforeEach, expect, it } from "vitest"
import {
  readStatementDraft,
  saveStatementDraft,
  type StatementDraft,
} from "./statement-review-draft"
const draft: StatementDraft = {
  revision: "first",
  rows: [
    {
      id: "1:0:2",
      excluded: false,
      date: "",
      description: "Unfinished correction",
      counterparty: "",
      amount_minor: "",
      direction: "debit",
      balance_minor: null,
      reason: "Checking source",
    },
  ],
  holder: "Holder",
  account: "Account",
  institution: "Bank",
  periodStart: "",
  periodEnd: "",
  detailsReason: "",
  amountText: { "1:0:2": "12." },
}
beforeEach(() => sessionStorage.clear())
it("restores incomplete edits exactly after a refresh", () => {
  expect(saveStatementDraft("user:case:file:first", draft)).toBe(true)
  expect(readStatementDraft("user:case:file:first", "first")).toEqual(draft)
})
it("preserves an unresolved credit or debit across a refresh", () => {
  const unresolved: StatementDraft = {
    ...draft,
    rows: draft.rows.map((row) => ({ ...row, direction: "" })),
  }
  expect(saveStatementDraft("draft", unresolved)).toBe(true)
  expect(readStatementDraft("draft", "first")?.rows[0].direction).toBe("")
})
it("restores separate date edits including an explicitly cleared posting date", () => {
  const dates: StatementDraft = {
    ...draft,
    rows: draft.rows.map((row) => ({
      ...row,
      date: "2023-01-02",
      date_values: { booking_date: "", value_date: "2023-01-05" },
    })),
  }
  expect(saveStatementDraft("dates", dates)).toBe(true)
  expect(readStatementDraft("dates", "first")).toEqual(dates)
})
it("does not apply edits to a changed extraction or another user's scope", () => {
  saveStatementDraft("user:case:file:first", draft)
  expect(readStatementDraft("user:case:file:first", "second")).toBeNull()
  expect(readStatementDraft("other-user:case:file:first", "first")).toBeNull()
})
it("ignores malformed saved data without losing the current review", () => {
  sessionStorage.setItem("draft", '{"rows":"broken"}')
  expect(readStatementDraft("draft", "first")).toBeNull()
  expect(readStatementDraft(null, "first")).toBeNull()
})
