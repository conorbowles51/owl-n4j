import type { QueueEntry } from "./review-queue"

/**
 * What a statement needs before it can be imported, field by field, and which
 * of those are optional. The same rules the server applies when it checks a
 * statement for import:
 *  - currency: the statement must have one (batch readiness);
 *  - bank, start and end dates: statement_admission blocks without them (a
 *    start date may instead be confirmed as not printed);
 *  - account holder and account number: import_issues reports them as not
 *    identified, which blocks import;
 *  - opening and closing balance: the closing-balance check needs both, and a
 *    statement with no payments cannot be saved without at least one;
 *  - no payments: a statement with none needs a person to confirm the period
 *    had none (unless the statement prints zero counts); listed when the
 *    server asks for it or has not yet been able to check it.
 * Printed totals of money in and out are optional: an absent total blocks nothing.
 */
export type StatementNeed = {
  key: string
  /** As it reads in a sentence: "opening balance". */
  label: string
  required: boolean
  have: boolean
  /** Why it is needed, in a few words. */
  why: string
}

const present = (value: string | null | undefined) => value !== null && value !== undefined && value !== ""

export function statementNeeds(entry: QueueEntry): StatementNeed[] {
  const needs: StatementNeed[] = [
    { key: "opening", label: "opening balance", required: true, have: present(entry.opening_minor),
      why: "to check the payments add up" },
    { key: "closing", label: "closing balance", required: true, have: present(entry.closing_minor),
      why: "to check the payments add up" },
    { key: "period_start", label: "statement start date", required: true, have: !!entry.period_start,
      why: "to know which dates it covers (or confirm none is printed)" },
    { key: "period_end", label: "statement end date", required: true, have: !!entry.period_end,
      why: "to know which dates it covers" },
    { key: "account", label: "account number", required: true, have: !!entry.account,
      why: "to know which account it belongs to" },
    { key: "holder", label: "account holder", required: true, have: !!entry.holder,
      why: "to know whose account it is" },
    { key: "institution", label: "bank", required: true, have: !!entry.institution,
      why: "to know which bank's account it is" },
    { key: "currency", label: "currency", required: true, have: !!entry.currency,
      why: "the amounts are in it" },
  ]
  // Asked for when the server says so, or when the statement stopped at "no
  // payments and no balance", before that question could be checked.
  const words = [entry.issue || "", ...entry.issue_messages].join(" ")
  if (entry.transaction_count === 0 && (entry.reasons.includes("no_activity") || /statement without transactions/i.test(words)))
    needs.push({ key: "no_activity", label: "confirmation that the period had no payments", required: true,
      have: false, why: "no payments were read; check every page first" })
  needs.push({ key: "totals", label: "printed totals of money in and out", required: false, have: false,
    why: "only if the statement prints them" })
  return needs
}

/** The required details still missing, in the order a person would fill them. */
export const missingRequired = (entry: QueueEntry) =>
  statementNeeds(entry).filter((need) => need.required && !need.have)

/** The details a save filled: missing before, present after. */
export function filledBySave(before: QueueEntry, after: QueueEntry) {
  const had = new Map(statementNeeds(before).map((need) => [need.key, need.have]))
  return statementNeeds(after).filter((need) => need.key !== "no_activity" && need.have && had.get(need.key) === false)
}

/** "opening balance, closing balance and account number" */
export function listWords(words: string[]) {
  if (words.length <= 1) return words.join("")
  return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`
}
