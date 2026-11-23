import type { TutorialStep } from "../types"

const SEARCH = ['input[aria-label="Search payments"]']

/** Where did the money go? Followed on the demo case through Travis Kell's account after the theft nights. */
export const MONEY: TutorialStep[] = [
  {
    title: "Open the money in the case",
    body: "Open Financial from the side menu. Overview totals every payment read from the statements, for all accounts and dates.",
    expect: "Money in this scope: 4 accounts, Oct 2023 to Jun 2024. Money in +225,413.55 USD, money out −115,135.48 USD.",
    shot: "money-overview",
    alt: "The Financial overview with the totals box marked: 4 accounts, money in 225,413.55 USD, money out 115,135.48 USD.",
    open: { to: "financial?view=overview", target: ["text=Overview"] },
  },
  {
    title: "Find the cash deposits",
    body: "Open Transactions and type CASH in Search payments. The list keeps only the payments whose statement line holds the word.",
    expect:
      "3 of 210 payments: cash paid into Travis Kell's account, 9,800.00 USD on 18 March, 9,650.00 USD on 15 April and 9,850.00 USD on 3 June 2024. Each is a few days after a theft night.",
    shot: "money-cash",
    alt: "Transactions searched for CASH, with the count 3 of 210 imported transactions marked.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Find who was paid",
    body: "Search payments again, this time for POCKETWIRE, the payment app on Kell's statements. Each line names who received the money.",
    expect:
      "6 payments out of Kell's account: 500.00 USD to Lena Marsh on 16 March, 13 April and 1 June, and 1,200.00 USD to Desmond Okafor on 17 March, 14 April and 2 June 2024.",
    shot: "money-pocketwire",
    alt: "Transactions searched for POCKETWIRE, with the count 6 of 210 imported transactions marked.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Open a payment's details",
    body: "Click Details on a payment. It shows the date, the account, the balance printed on the statement, and buttons to add the payment to a theory, Corroborate it or open its statement.",
    expect: "For the 18 March cash deposit: payment number 183, account TRAVIS KELL · Kestrel Point Bank · 7730554471, printed balance 14,024.38 USD.",
    shot: "money-details",
    alt: "A cash deposit's details open, with the Open original statement button marked.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Check the line on the statement",
    body: "Click Open original statement. The panel shows the line as the bank printed it and says whether it was checked against the statement's balances.",
    expect: "CASH DEPOSIT BR 014 FENWICK, money in 9,800.00 USD, dated 2024-03-18, Checked against the statement's balances.",
    shot: "money-statement",
    alt: "The statement panel for the 9,800.00 USD cash deposit, showing the line as printed on the statement.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "See what the ledger still lacks",
    body: "Five theft nights but payments after only three: go back to Overview. NEXT FOR YOU lists statements that wait for a person before their payments count.",
    expect: "1 statement needs a check: Kell's May statement, whose second page is missing. Its payments stay out of the totals until a person checks it.",
    shot: "money-held",
    alt: "The Financial overview with the Check the 1 statement button marked.",
    open: { to: "financial?view=overview", target: ["text=Check the"] },
  },
  {
    title: "Follow one payment to both accounts",
    body: "Search payments for BAY 4 RENT. A payment between two accounts in the case shows twice: once leaving one account and once arriving in the other.",
    expect: "14 payments of 650.00 USD: rent for bay 4, out of Kell's account and into Ruiz Auto & Tire's on the 1st of the month, from October 2023, before the first theft.",
    shot: "money-rent",
    alt: "Transactions searched for BAY 4 RENT, with the count 14 of 210 imported transactions marked.",
    open: { to: "financial?view=transactions", target: SEARCH },
  },
  {
    title: "Keep what you found",
    body: "Record the pattern as a finding and attach its payments: Findings & Observations, then Create finding. From a payment's details, Add to theory files it with a theory as evidence for or against.",
    expect: "Findings & Observations with its Create finding button. The demo case has no saved findings yet.",
    shot: "money-findings",
    alt: "Findings & Observations with the Create finding button marked.",
    open: { to: "financial?view=findings", target: ["text=Create finding"] },
  },
]
