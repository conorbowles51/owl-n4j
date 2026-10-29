import { expect, it } from "vitest"
import { guidanceFor } from "./queue-guidance"
import { savedOutcome, type QueueEntry, type ReviewQueue } from "./review-queue"
import { filledBySave, missingRequired, statementNeeds } from "./statement-needs"

const GATE = "Enter at least one printed opening or closing balance to save a statement without transactions."
// The shape of CommitmentLetter (3).pdf in OPDMD66: bank, holder and currency read; nothing else; no payments.
const entry = (over: Partial<QueueEntry> = {}): QueueEntry => ({
  id: "i1", batch_id: "b1", file_id: "f1", source_id: "f1", statement_id: null, filename: "CommitmentLetter (3).pdf",
  holder: "Keny V Alvarado Gomez", account: "", institution: "Truist Bank", currency: "USD", period_start: "",
  period_end: "", page: 1, can_import: false, status: "attention", bucket: "waiting", file_ids: ["f1"],
  file_position: 1, file_statements: 1, other_problems: 0, problem_total: 1, reasons: ["reading"], also: [],
  fix_makes_ready: false, issue_pages: [], issue_messages: [GATE], why: [], issue: GATE, issue_reason: "reading",
  opening_minor: null, closing_minor: null, transaction_count: 0, ...over,
})
const queue = (items: QueueEntry[], ready: QueueEntry[] = []) =>
  ({ items, ready, filled: [], unreadable: [] }) as unknown as ReviewQueue

it("lists every detail import needs at once, each marked required or optional", () => {
  const needs = statementNeeds(entry())
  expect(missingRequired(entry()).map((need) => need.label)).toEqual([
    "opening balance", "closing balance", "statement start date", "statement end date", "account number",
    "confirmation that the period had no payments",
  ])
  expect(needs.filter((need) => need.have).map((need) => need.label)).toEqual(["account holder", "bank", "currency"])
  expect(needs.filter((need) => !need.required).map((need) => need.label)).toEqual(["printed totals of money in and out"])
})

it("asks to confirm no payments only when the server asks or could not yet check it", () => {
  const read = entry({ issue: "Closing balance off by 1.00 USD", issue_messages: [], reasons: ["balance"], issue_reason: "balance" })
  expect(statementNeeds(read).some((need) => need.key === "no_activity")).toBe(false)
  expect(statementNeeds({ ...read, reasons: ["no_activity"] }).some((need) => need.key === "no_activity")).toBe(true)
  expect(statementNeeds({ ...entry(), transaction_count: 4 }).some((need) => need.key === "no_activity")).toBe(false)
})

it("after a save says what was saved and exactly what is still needed and why, never a bare Still needs", () => {
  const after = entry({ opening_minor: "125000", issue: "Enter the statement start date printed on this statement.",
    issue_messages: ["Enter the statement start date printed on this statement."] })
  expect(filledBySave(entry(), after).map((need) => need.label)).toEqual(["opening balance"])
  expect(savedOutcome(queue([after]), entry())).toEqual({
    held: true,
    message:
      "Saved your opening balance. Still needed before it can be imported: closing balance, statement start date, " +
      "statement end date and account number. Why it is held: Enter the statement start date printed on this statement.",
  })
  const done = entry({ opening_minor: "1", closing_minor: "1", period_start: "2024-01-01", period_end: "2024-01-31",
    account: "1234" })
  expect(savedOutcome(queue([], [done]), after).message).toBe(
    "Saved your closing balance, statement start date, statement end date and account number. Ready to import: use Import at the top of the queue."
  )
})

it("guides a statement with no payments and no balances to check it is a statement first", () => {
  const guide = guidanceFor(entry())
  expect(guide.title).toBe("No payments and no balances were read from this statement")
  expect(guide.steps[1]).toBe("Check that it is a bank or card statement. If it is not, choose This isn't a statement.")
})
