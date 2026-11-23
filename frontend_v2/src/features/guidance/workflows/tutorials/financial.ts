import type { TutorialStep } from "../types"

const SEARCH = ['input[aria-label="Search payments"]']

/** Check and correct what Loupe read. */
export const LOUPE_CALLS: TutorialStep[] = [
  {
    title: "Count the calls Loupe made",
    body: "Open Financial. Spot-check Loupe counts the values Loupe chose where a statement does not print them outright, such as who was paid or a category.",
    expect: "49 calls Loupe made for you, 49 open.",
    shot: "fin-calls",
    alt: "The Financial overview with the Spot-check Loupe count marked.",
    open: { to: "financial?view=overview", target: ["text=calls Loupe made for you"] },
  },
  {
    title: "Open the judgement calls",
    body: "Statements & accounts, then Judgement calls. Each call gives the sentence behind it and the page it came from.",
    expect: "Judgement calls (49 to check).",
    shot: "fin-judgement",
    alt: "The judgement calls on a statement, marked.",
    open: { to: "financial?view=statements", target: ['[data-guide="financial-judgement-calls"]', "text=Judgement calls"] },
  },
  {
    title: "Look at the call on its page",
    body: "Show on page opens the statement at the line. Compare the value Loupe chose with what the page prints.",
    expect: "Each call names its statement and page.",
    shot: "fin-judgement",
    alt: "The judgement calls on a statement.",
    open: { to: "financial?view=statements", target: ['[data-guide="financial-judgement-calls"]', "text=Judgement calls"] },
  },
  {
    title: "Mark it or correct it",
    body: "Looks right is one click and is kept under your name. Correct it opens the value and asks why. The value read stays beside your correction, and only your value counts in totals and searches.",
    expect: "Looks right and Correct it beside each call.",
    shot: "fin-judgement",
    alt: "A judgement call with Looks right and Correct it.",
    open: { to: "financial?view=statements", target: ['[data-guide="financial-judgement-calls"]', "text=Judgement calls"] },
  },
  {
    title: "Name who was paid",
    body: "On Transactions, a payment with Not identified under To waits for a name. Name it on one payment, or Name them one by one for every payment in view.",
    expect: "POCKETWIRE: 6 payments in view with the counterparty not identified, and Name them one by one.",
    shot: "fin-name",
    alt: "Transactions searched for POCKETWIRE, with Name them one by one marked.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Check a category Loupe guessed",
    body: "A category marked Model guess was chosen by a model, not a person. Open Details on the payment to change it; your choice replaces the guess.",
    expect: "The 16 March payment to Lena Marsh, 500.00 USD: Peer-to-peer payments, Model guess.",
    shot: "fin-name",
    alt: "A payment with its category marked Model guess.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
]

/** Decide on possible copies of a statement. */
export const STATEMENT_COPIES: TutorialStep[] = [
  {
    title: "See which statements wait",
    body: "Open Financial, Statements & accounts. The count says how many statements are done, how many wait for you, and how many were set aside as copies.",
    expect: "22 statements: Imported 20, Waiting for you 1, Copies set aside 1.",
    shot: "fin-statements",
    alt: "Statements & accounts with the statement counts.",
    open: { to: "financial?view=statements" },
  },
  {
    title: "Open the copies set aside",
    body: "Review queue, then Copies set aside. Each copy names the statement kept instead. A statement that may be a copy and is not yet decided waits under Needs you, marked May be a copy of.",
    expect: "kell-2024-04.pdf, Kell's April statement, set aside as a copy of states-exhibit-14-kell-april-2024.pdf, the same statement produced as the State's Exhibit 14, which was kept and imported. The copy counts nothing.",
    shot: "fin-compare",
    alt: "The copy set aside, with its Compare button marked.",
    open: { to: "financial?view=statements", target: ["text=Review queue"] },
  },
  {
    title: "Compare the two side by side",
    body: "Compare opens Compare side by side: the facts of both statements in one table, then both pages next to each other.",
    expect: "All 10 facts agree: bank, account, holder, period, currency, opening balance 19,059.49 USD, closing balance 30,430.82 USD, money in, money out and 14 payments.",
    shot: "fin-compare-open",
    alt: "Compare side by side with the table of facts marked, every row Agrees.",
    open: { to: "financial?view=statements", target: ["text=Review queue"] },
  },
  {
    title: "Keep it set aside, or restore it",
    body: "A copy set aside stays in the case with its corrections and counts nothing. If it must be imported after all, Restore for comparison puts it back in review, with your reason.",
    expect: "Duplicate - Ignored by system, with Open retained original and Restore for comparison.",
    shot: "fin-compare-open",
    alt: "Compare side by side for the April statement and the State's Exhibit 14.",
    open: { to: "financial?view=statements", target: ["text=Review queue"] },
  },
  {
    title: "Check the totals count it once",
    body: "Back on Overview, the totals count each payment once. Which months do we have? shows the months the kept statements cover.",
    expect: "4 accounts, Oct 2023 to Jun 2024, money in +225,413.55 USD.",
    shot: "money-overview",
    alt: "The Financial overview totals, marked.",
    open: { to: "financial?view=overview", target: ["text=Overview"] },
  },
]
