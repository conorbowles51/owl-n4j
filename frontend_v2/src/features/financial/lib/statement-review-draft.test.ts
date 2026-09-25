import { beforeEach, expect, it } from "vitest"
import {
  serverStatementDraft,
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
it("retains a recognised undated charge when the review is reopened", () => {
  const undated = {
    ...draft,
    rows: [{ ...draft.rows[0], date_unprinted: true }],
  }
  expect(saveStatementDraft("undated", undated)).toBe(true)
  expect(readStatementDraft("undated", "first")).toEqual(undated)
})
it("restores all payments and retained headings from a long statement", () => {
  const longDraft: StatementDraft = {
    ...draft,
    rows: Array.from({ length: 1240 }, (_, index) => ({
      ...draft.rows[0],
      id: String(index),
      excluded: index >= 1000,
    })),
  }
  expect(saveStatementDraft("long", longDraft)).toBe(true)
  expect(readStatementDraft("long", "first")).toEqual(longDraft)
  expect(
    saveStatementDraft("too-long", {
      ...longDraft,
      rows: Array.from({ length: 100001 }, () => draft.rows[0]),
    })
  ).toBe(false)
})
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

it("restores older server drafts with unknown dates and optional raw fields", () => {
  const restored = serverStatementDraft({
    expected_revision: "a",
    holder: "Saved company",
    period_start: null,
    period_end: null,
    rows: [
      {
        id: "manual:one",
        excluded: false,
        date: null,
        direction: null,
        amount_minor: null,
        description: "Still editing",
      },
    ],
  })
  expect(restored?.holder).toBe("Saved company")
  expect(restored?.periodStart).toBe("")
  expect(restored?.rows[0]).toMatchObject({
    description: "Still editing",
    date: "",
    direction: "",
    amount_minor: "",
    balance_minor: null,
  })
})

it("retains a manually positioned payment and its reference after save and reload", () => {
  const positioned: StatementDraft = {
    ...draft,
    rows: [
      {
        ...draft.rows[0],
        id: "manual:payment",
        manual_page: 2,
        source_order_anchor: { relation: "after", row_id: "2:0:4" },
      },
    ],
  }
  expect(saveStatementDraft("positioned", positioned)).toBe(true)
  expect(
    readStatementDraft("positioned", "first")?.rows[0].source_order_anchor
  ).toEqual({ relation: "after", row_id: "2:0:4" })
  expect(
    serverStatementDraft({ expected_revision: "first", rows: positioned.rows })
      ?.rows[0].source_order_anchor
  ).toEqual({ relation: "after", row_id: "2:0:4" })
})
