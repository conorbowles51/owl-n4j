import type { QueueCounts, QueueEntry } from "./review-queue"

/**
 * What a queue entry asks of the investigator, in plain words: a short title,
 * numbered steps (what to open, where to look, what to enter) and what happens
 * after. Every reason the server gives maps here; an unknown one still gets
 * steps that say what to do. Nothing here names an internal code.
 */
export type Guidance = {
  title: string
  steps: string[]
  /** What happens once she has done it. */
  after: string
  /** The one button: opens the statement at the page or field the steps name. */
  action: string
}

/** Someone the queue can address: the signed-in user, or who saved the held work. */
export type QueuePerson = { id?: string | null; name?: string | null }

const firstName = (name?: string | null) => (name || "").trim().split(/\s+/)[0] || ""

/**
 * "Needs Maria": the person an item waits for. Held work someone saved
 * themselves (their corrections, rows they added) names them when they are
 * not the person looking; otherwise the signed-in user, or "you".
 */
export function needsLabel(user?: QueuePerson | null, entry?: Pick<QueueEntry, "worked_by">) {
  const worker = entry?.worked_by
  if (worker && worker.user_id !== (user?.id ?? "") && firstName(worker.name)) return `Needs ${firstName(worker.name)}`
  const mine = firstName(user?.name)
  return mine ? `Needs ${mine}` : "Needs you"
}

/** "Maria's" when someone else saved the held work, else "Your". */
function whose(user: QueuePerson | null | undefined, entry: QueueEntry) {
  const worker = entry.worked_by
  if (worker && worker.user_id !== (user?.id ?? "") && firstName(worker.name)) return `${firstName(worker.name)}'s`
  return "Your"
}

const pageList = (pages: number[]) =>
  pages.length === 0
    ? ""
    : pages.length === 1
      ? `page ${pages[0]}`
      : pages.length <= 4
        ? `pages ${pages.slice(0, -1).join(", ")} and ${pages[pages.length - 1]}`
        : `pages ${pages[0]} to ${pages[pages.length - 1]}`

/** Every page the issue is on, else the statement's first page. */
export function entryPages(entry: QueueEntry) {
  if (entry.issue_pages.length) return entry.issue_pages
  return typeof entry.page === "number" ? [entry.page] : []
}

const FIELD_WORDS: Record<string, { name: string; where: string }> = {
  currency: { name: "currency", where: "the currency code or symbol next to the amounts, or in the account summary" },
  institution: { name: "bank name", where: "the bank's name or logo at the top of the page" },
  holder: { name: "account holder", where: "the name and address block at the top of the page" },
  account: { name: "account number", where: "the account number near the top of the page" },
  dates: { name: "statement dates", where: "the statement period (from and to dates) near the top of the page" },
}

const PROPOSAL_FIELD: Record<string, string> = {
  currency: "currency",
  institution: "institution",
  holder: "holder",
  account: "account_number",
}

/** The proposal (if any) for the detail a reason asks for. */
export function reasonProposal(entry: QueueEntry, reason = entry.issue_reason || "") {
  const field = PROPOSAL_FIELD[reason]
  return field ? entry.proposals?.[field] : undefined
}

const SAVES = "Loupe checks it again and imports it by itself once everything adds up."

function manualRow(entry: QueueEntry) {
  return [entry.issue || "", ...entry.issue_messages].some((text) => /manually added (transaction|row)/i.test(text))
}

/** The plain instruction for one queue entry. */
export function guidanceFor(entry: QueueEntry, user?: QueuePerson | null, bucket = entry.bucket): Guidance {
  const pages = entryPages(entry)
  const where = pageList(pages)
  const onPage = where ? ` on ${where}` : ""
  const openWhere = where ? `Open the PDF at ${where}.` : "Open the statement."
  const action = where ? `Open ${pages.length === 1 ? where : `page ${pages[0]}`}` : "Open the statement"
  if (bucket === "unreadable" || entry.issue_reason === "unreadable")
    return {
      title: "Nothing could be read from this statement",
      steps: [
        openWhere,
        "Check that it is a bank or card statement and that the pages are legible.",
        "If it is not a statement, choose Leave out. If it is, enter its opening and closing balances and its payments.",
      ],
      after: SAVES,
      action,
    }
  const reason = entry.issue_reason || ""
  const field = FIELD_WORDS[reason]
  const proposal = reasonProposal(entry, reason)
  switch (reason) {
    case "import_failed":
      return {
        title: "The import did not finish",
        steps: ["Open the statement.", "Press Import again.", "If it stops again, the statement shows why."],
        after: "It moves to Imported once it saves.",
        action: "Open the statement",
      }
    case "saved_review":
      return {
        title: `${whose(user, entry)} saved corrections were made before Loupe read the PDF again`,
        steps: [
          "Open the statement.",
          "Compare the saved corrections with what Loupe reads now, shown side by side.",
          "Keep the corrections that still apply, then save.",
        ],
        after: SAVES,
        action: "Compare corrections",
      }
    case "reprint":
      return {
        title: "The PDF prints this statement twice and the copies differ",
        steps: [
          openWhere,
          "Compare the two printed copies of the period.",
          "Choose the copy whose totals match the bank's printed balances.",
        ],
        after: SAVES,
        action,
      }
    case "assignment":
      return {
        title: "Payments are not linked to an account",
        steps: ["Open the statement.", "Choose the account the payments belong to.", "Save."],
        after: SAVES,
        action: "Choose the account",
      }
    case "principal_only":
      return {
        title: "The opening amount owed is not printed",
        steps: [
          openWhere,
          "Find the amount owed at the start of the period: the loan summary, or the closing amount on the previous statement.",
          "Enter it as the opening balance and save.",
        ],
        after: SAVES,
        action,
      }
    case "currency":
    case "institution":
    case "holder":
    case "account":
    case "dates":
      if (proposal && !proposal.confirmed)
        return {
          title: `Confirm the ${field.name}: ${proposal.value}`,
          steps: [
            `${openWhere} Look for ${field.where}.`,
            `If it is ${proposal.value}, press Confirm. Loupe suggests it from: ${proposal.label}.`,
            `If it is something else, enter the right ${field.name} instead.`,
          ],
          after: SAVES,
          action: `Confirm ${proposal.value}`,
        }
      return {
        title: `The ${field.name} is not printed where Loupe looks`,
        steps: [
          `${openWhere} Look for ${field.where}.`,
          `Enter the ${field.name} below, or in the statement.`,
          "Save.",
        ],
        after: SAVES,
        action: `Enter the ${field.name}`,
      }
    case "balance": {
      const text = entry.issue || ""
      if (/opening or closing balance not read/i.test(text))
        return {
          title: "The opening and closing balances were not read",
          steps: [
            openWhere,
            "Find the printed opening (previous) balance and closing (new) balance, usually in the account summary.",
            "Enter both and save.",
          ],
          after: "Loupe adds up the payments against them and imports the statement once they match.",
          action,
        }
      const off = text.match(/closing balance off by (.+)$/i)
      if (off)
        return {
          title: `The payments miss the printed closing balance by ${off[1]}`,
          steps: [
            openWhere,
            "Compare each payment Loupe read with the PDF. Look for a missing row, or an amount read wrong.",
            "Add the missing row or correct the amount, then save.",
          ],
          after: SAVES,
          action,
        }
      if (/printed balances? (does|do) not add up/i.test(text))
        return {
          title: `A printed running balance does not add up${onPage}`,
          steps: [
            openWhere,
            "Check the rows just above the highlighted balance against the PDF.",
            "Correct the amount that was read wrong, or add the missing row, then save.",
          ],
          after: SAVES,
          action,
        }
      if (/printed total/i.test(text))
        return {
          title: `A printed total does not match the payments${onPage}`,
          steps: [
            openWhere,
            "Compare the printed total with the payments listed above it.",
            "Add the missing row or correct the amount, then save.",
          ],
          after: SAVES,
          action,
        }
      return {
        title: "The balances do not add up",
        steps: [openWhere, "Compare the payments with the PDF.", "Correct what was read wrong, then save."],
        after: SAVES,
        action,
      }
    }
    case "incomplete":
      return {
        title: `Some payments are missing a date or amount${onPage}`,
        steps: [openWhere, "Find each highlighted row in the PDF.", "Enter its missing date or amount, then save."],
        after: SAVES,
        action,
      }
    case "count":
      return {
        title: "The statement prints more payments than Loupe read",
        steps: [
          "Open the statement.",
          "Compare the printed number of payments with the rows Loupe read.",
          "Add the missing rows, then save.",
        ],
        after: SAVES,
        action: "Open the statement",
      }
    case "no_activity":
      return {
        title: "No payments were read: confirm the period had none",
        steps: [
          openWhere,
          "Check the statement prints no payments for the period (opening and closing balances are the same).",
          "If so, press Confirm no payments. If it has payments, open it and add them.",
        ],
        after: "It is imported with its balances and no payments.",
        action,
      }
  }
  if (manualRow(entry))
    return {
      title: `${whose(user, entry) === "Your" ? "A row you added" : `A row ${whose(user, entry).replace(/'s$/, "")} added`} needs its page`,
      steps: [
        "Open the statement.",
        "Find the row added by hand.",
        "Choose the page of the PDF it is printed on, then save.",
      ],
      after: SAVES,
      action: "Choose the page",
    }
  if (reason === "reading" && /unreadable/i.test(entry.issue || ""))
    return {
      title: `Some rows could not be read${onPage}`,
      steps: [
        openWhere,
        "Read each highlighted row in the PDF.",
        "Enter or correct its date and amount, or mark it as not a payment. Then save.",
      ],
      after: SAVES,
      action,
    }
  // Any other check: the statement shows it highlighted.
  return {
    title: entry.issue || "This statement needs a check",
    steps: [
      openWhere,
      "The problem is highlighted in the statement.",
      "Fix it as the statement describes, then save.",
    ],
    after: SAVES,
    action,
  }
}

/** Short filter-chip labels, most important first; same words as the titles. */
export const ISSUE_LABELS: Record<string, string> = {
  import_failed: "Import did not finish",
  saved_review: "Saved corrections to compare",
  reprint: "Printed twice",
  assignment: "Payments need an account",
  principal_only: "Opening amount owed",
  currency: "Currency",
  institution: "Bank name",
  holder: "Account holder",
  account: "Account number",
  dates: "Statement dates",
  balance: "Balances",
  incomplete: "Missing dates or amounts",
  count: "Missing payments",
  no_activity: "No payments",
  reading: "Rows to check",
}

/** A label for any reason, including one this screen does not know yet. */
export const issueLabel = (reason: string) => ISSUE_LABELS[reason] ?? "Other checks"

/** One answer for many statements: same account, same question, same proposal. */
export type QueueGroup = { key: string; reason: string; entries: QueueEntry[]; proposal?: { value: string; label: string } }

const GROUPABLE = new Set(["currency", "institution", "holder", "account", "no_activity"])

/**
 * Entries in the order given, with statements of one account waiting for the
 * same answer gathered into one group. A group needs at least two statements
 * and a known account (number, or bank and holder); everything else stays one
 * item per statement.
 */
export function groupEntries(entries: QueueEntry[], keepApart: string[] = []): (QueueEntry | QueueGroup)[] {
  const keyOf = (entry: QueueEntry) => {
    const reason = entry.issue_reason || ""
    if (!GROUPABLE.has(reason) || keepApart.includes(reason) || entry.reasons.length > 1) return ""
    const account = entry.account || (entry.institution && entry.holder ? `${entry.institution}|${entry.holder}` : "")
    if (!account) return ""
    const proposal = reasonProposal(entry, reason)
    return `${reason}|${account}|${proposal && !proposal.confirmed ? proposal.value : ""}`
  }
  const groups = new Map<string, QueueEntry[]>()
  for (const entry of entries) {
    const key = keyOf(entry)
    if (key) groups.set(key, [...(groups.get(key) ?? []), entry])
  }
  const result: (QueueEntry | QueueGroup)[] = []
  const placed = new Set<string>()
  for (const entry of entries) {
    const key = keyOf(entry)
    const members = key ? groups.get(key)! : []
    if (members.length < 2) {
      result.push(entry)
      continue
    }
    if (placed.has(key)) continue
    placed.add(key)
    const proposal = reasonProposal(members[0])
    result.push({
      key,
      reason: members[0].issue_reason || "",
      entries: members,
      proposal: proposal && !proposal.confirmed ? { value: proposal.value, label: proposal.label } : undefined,
    })
  }
  return result
}

export const isGroup = (item: QueueEntry | QueueGroup): item is QueueGroup => "entries" in item

const accountName = (entry: QueueEntry) =>
  [entry.institution, entry.account ? `account ${entry.account}` : entry.holder].filter(Boolean).join(" ")

/** The instruction for a group: one check, one answer, every statement saved together. */
export function groupGuidance(group: QueueGroup): Guidance {
  const n = group.entries.length
  const first = group.entries[0]
  const field = FIELD_WORDS[group.reason]
  const account = accountName(first)
  const pages = entryPages(first)
  const look = `Open one of them${pages.length ? ` at page ${pages[0]}` : ""}`
  if (group.reason === "no_activity")
    return {
      title: `${n} statements of ${account} have no payments: confirm the periods had none`,
      steps: [
        `${look} and check it prints no payments (opening and closing balances are the same).`,
        "If that is right for all of them, press Confirm. Any with payments is left out of the confirmation with its reason.",
      ],
      after: "They are imported with their balances and no payments.",
      action: `Confirm no payments for ${n}`,
    }
  if (group.proposal)
    return {
      title: `${n} statements of ${account}: confirm the ${field.name} is ${group.proposal.value}`,
      steps: [
        `${look}. Look for ${field.where}.`,
        `If it is ${group.proposal.value}, press Confirm once for all ${n}. Loupe suggests it from: ${group.proposal.label}.`,
        `If not, enter the right ${field.name} once below.`,
      ],
      after: SAVES,
      action: `Confirm ${group.proposal.value} for ${n}`,
    }
  return {
    title: `${n} statements of ${account} need the ${field?.name ?? "same detail"}`,
    steps: [`${look}. Look for ${field?.where ?? "the detail"}.`, `Enter it once below; it is saved on all ${n}.`],
    after: SAVES,
    action: `Save for all ${n}`,
  }
}

/** Values Loupe filled itself: what, which value, and why. */
export type FilledMark = { field: string; name: string; value: string; basis: string }

const MARK_NAMES: Record<string, string> = {
  currency: "Currency",
  institution: "Bank",
  holder: "Account holder",
  account_number: "Account number",
}

export function filledMarks(entry: QueueEntry): FilledMark[] {
  return Object.entries(entry.proposals ?? {})
    .filter(([, proposal]) => proposal.confirmed)
    .map(([field, proposal]) => ({
      field,
      name: MARK_NAMES[field] ?? "Detail",
      value: proposal.value,
      basis: proposal.label,
    }))
}

/** The work the investigator does: statements waiting for her, and statements nothing could be read from. */
export function needsCount(counts: QueueCounts) {
  return counts.waiting + counts.unreadable + counts.unreadable_files
}

/** Everything Loupe moves on by itself; none of it needs her. */
export const HANDLED_PARTS: {
  list: "ready" | "filled" | "reader" | "copies" | "rechecking" | "saving"
  count: (c: QueueCounts) => number
  label: string
  line: string
}[] = [
  {
    list: "filled",
    count: (c) => c.filled,
    label: "Details filled by Loupe",
    line: "Loupe found the missing details in the same account's saved statements. They are filled and imported when you press Import.",
  },
  {
    list: "ready",
    count: (c) => c.ready,
    label: "Ready to import",
    line: "Every check passes. Press Import to add them to the ledger.",
  },
  {
    list: "rechecking",
    count: (c) => c.rechecking,
    label: "Being checked again",
    line: "Loupe is checking these again now. They come back to you only if they need a person.",
  },
  {
    list: "saving",
    count: (c) => c.saving,
    label: "Importing now",
    line: "Being added to the ledger.",
  },
  {
    list: "reader",
    count: (c) => c.reader_fix,
    label: "Waiting for a better reader",
    line: "Loupe cannot read these files reliably yet. Nothing to do by hand: they are read again when the reader improves.",
  },
  {
    list: "copies",
    count: (c) => c.copies,
    label: "Copies set aside",
    line: "Copies of statements already in the case. They count nothing.",
  },
]

export function handledCount(counts: QueueCounts) {
  return HANDLED_PARTS.reduce((sum, part) => sum + part.count(counts), 0)
}
