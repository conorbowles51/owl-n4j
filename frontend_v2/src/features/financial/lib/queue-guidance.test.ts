import { expect, it } from "vitest"
import {
  filledMarks,
  groupEntries,
  groupGuidance,
  guidanceFor,
  handledCount,
  isGroup,
  issueLabel,
  needsCount,
  needsLabel,
  type QueueGroup,
} from "./queue-guidance"
import type { QueueCounts, QueueEntry } from "./review-queue"

const entry = (over: Partial<QueueEntry> = {}): QueueEntry => ({
  id: "i1", batch_id: "b1", file_id: "f1", source_id: "f1", statement_id: "s1", filename: "Statement.pdf",
  holder: "Holder", account: "0001", institution: "Bank", currency: "", period_start: "2021-01-01",
  period_end: "2021-01-31", page: 3, can_import: false, status: "attention", bucket: "waiting", file_ids: ["f1"],
  file_position: 1, file_statements: 1, other_problems: 0, problem_total: 1, reasons: [], also: [],
  fix_makes_ready: false, issue_pages: [], issue_messages: [], why: [], ...over,
})
const me = { id: "u1", name: "Maria Lopez" }

// No internal code, batch or reading wording ever reaches her.
const JARGON = /copy_of_saved|not_all_held|issue_reason|_|\bbatch\b|\breading\b|lineage/i
const every = [
  "import_failed", "saved_review", "reprint", "assignment", "principal_only", "currency", "institution", "holder",
  "account", "dates", "balance", "incomplete", "count", "no_activity", "reading", "some_new_reason",
]

it("gives every reason a plain title, numbered steps that say where to look, one action and what happens next", () => {
  for (const reason of every) {
    const guide = guidanceFor(entry({ issue_reason: reason, issue: "" }), me)
    expect(guide.title, reason).toBeTruthy()
    expect(guide.steps.length, reason).toBeGreaterThanOrEqual(2)
    expect(guide.action, reason).toBeTruthy()
    expect(guide.after, reason).toBeTruthy()
    for (const text of [guide.title, ...guide.steps, guide.action, guide.after]) expect(text, reason).not.toMatch(JARGON)
    expect(issueLabel(reason)).not.toMatch(JARGON)
  }
})

it("names the page to open, and a page the issue is on before the statement's first page", () => {
  const guide = guidanceFor(entry({ issue_reason: "reading", issue: "3 rows unreadable on page 7", issue_pages: [7, 8] }), me)
  expect(guide.title).toBe("Some rows could not be read on pages 7 and 8")
  expect(guide.steps[0]).toBe("Open the PDF at pages 7 and 8.")
  expect(guide.action).toBe("Open page 7")
  expect(guidanceFor(entry({ issue_reason: "no_activity" }), me).action).toBe("Open page 3")
})

it("words each balance problem by what she must find in the PDF", () => {
  const balance = (issue: string) => guidanceFor(entry({ issue_reason: "balance", issue }), me)
  expect(balance("Opening or closing balance not read: enter both from the statement").title).toBe(
    "The opening and closing balances were not read"
  )
  expect(balance("Closing balance off by 12.50 USD").title).toBe("The payments miss the printed closing balance by 12.50 USD")
  expect(balance("2 printed balances do not add up on page 4").steps[1]).toMatch(/rows just above the highlighted balance/)
  expect(balance("A printed total does not agree with the payments").title).toMatch(/printed total/)
})

it("asks for a one-press confirm when Loupe proposes the value, and says where the proposal came from", () => {
  const guide = guidanceFor(entry({ issue_reason: "currency", proposals: {
    currency: { value: "USD", label: "same account's 3 saved statements, all USD", confirmed: false } } }), me)
  expect(guide.title).toBe("Confirm the currency: USD")
  expect(guide.action).toBe("Confirm USD")
  expect(guide.steps[1]).toContain("same account's 3 saved statements, all USD")
  expect(guidanceFor(entry({ issue_reason: "holder" }), me).action).toBe("Enter the account holder")
})

it("tells her about a row added by hand that needs its page, naming who added it", () => {
  const manual = entry({ issue_reason: "reading", issue: "A manually added transaction needs a page from this PDF.",
    issue_messages: ["A manually added transaction needs a page from this PDF."] })
  expect(guidanceFor(manual, me).title).toBe("A row you added needs its page")
  expect(guidanceFor({ ...manual, worked_by: { user_id: "u2", name: "Sam Diaz" } }, me).title).toBe("A row Sam added needs its page")
  expect(guidanceFor(manual, me).action).toBe("Choose the page")
})

it("labels what needs a person with the signed-in user's first name, or the colleague whose work is held", () => {
  expect(needsLabel(me)).toBe("Needs Maria")
  expect(needsLabel(null)).toBe("Needs you")
  expect(needsLabel({ id: "u1", name: "" })).toBe("Needs you")
  expect(needsLabel(me, { worked_by: { user_id: "u2", name: "Sam Diaz" } })).toBe("Needs Sam")
  expect(needsLabel(me, { worked_by: { user_id: "u1", name: "Maria Lopez" } })).toBe("Needs Maria")
  const saved = entry({ issue_reason: "saved_review", worked_by: { user_id: "u2", name: "Sam Diaz" } })
  expect(guidanceFor(saved, me).title).toBe("Sam's saved corrections were made before Loupe read the PDF again")
})

it("gathers one account's statements waiting for the same answer into one item with one confirm", () => {
  const proposal = { currency: { value: "EUR", label: "same account's 4 saved statements", confirmed: false } }
  const list = [
    entry({ id: "a", issue_reason: "currency", proposals: proposal }),
    entry({ id: "b", issue_reason: "balance", issue: "Closing balance off by 1.00 EUR" }),
    entry({ id: "c", issue_reason: "currency", proposals: proposal }),
    entry({ id: "d", issue_reason: "currency", account: "0002", proposals: proposal }),
    entry({ id: "e", issue_reason: "currency", reasons: ["currency", "balance"], proposals: proposal }),
  ]
  const grouped = groupEntries(list)
  expect(grouped.map((item) => (isGroup(item) ? item.entries.map((e) => e.id).join("+") : item.id))).toEqual([
    "a+c", "b", "d", "e",
  ])
  const group = grouped[0] as QueueGroup
  const guide = groupGuidance(group)
  expect(guide.title).toBe("2 statements of Bank account 0001: confirm the currency is EUR")
  expect(guide.action).toBe("Confirm EUR for 2")
  // A reason kept apart (chosen with its own ticks) is never grouped.
  expect(groupEntries(list.map((e) => ({ ...e, issue_reason: "no_activity" })), ["no_activity"]).some(isGroup)).toBe(false)
})

it("marks every value Loupe filled with where it came from", () => {
  expect(filledMarks(entry({ proposals: {
    currency: { value: "USD", label: "same account's 3 saved statements", confirmed: true },
    holder: { value: "X", label: "guess", confirmed: false },
  } }))).toEqual([{ field: "currency", name: "Currency", value: "USD", basis: "same account's 3 saved statements" }])
})

it("splits the counts into what needs a person and what Loupe handles", () => {
  const counts = { imported: 9, saving: 1, waiting: 4, filled: 2, reader_fix: 3, ready: 5, copies: 6, unreadable: 1,
    unreadable_files: 2, removed_files: 0, copy_files: 0, rechecking: 7, left_unimported: 0, assigned: 0,
    unexplained: 0, not_payment: 0 } satisfies QueueCounts
  expect(needsCount(counts)).toBe(7)
  expect(handledCount(counts)).toBe(24)
})
