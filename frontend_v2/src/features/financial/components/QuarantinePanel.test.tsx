/**
 * The four states a quarantine list cannot be in the middle of, and the three
 * claims this panel makes about the rows it did get.
 *
 * The hook is mocked rather than the network, on the same reasoning as
 * `LedgerPanel.test.tsx`: what is under test is the panel's reading of a query
 * result, not the query. `LedgerTable` is left real, so the grounds column
 * being asked for can be shown to actually arrive.
 *
 * Two things get the most attention. The first is the status the panel sends,
 * because a panel whose every sentence is about quarantine reading some other
 * population is a screen that lies in the most direct way available to it. The
 * second is the empty case: zero quarantined rows is a good result, and copy
 * borrowed from the general ledger panel would state the reverse of what was
 * checked.
 */

import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { LedgerResponse, LedgerTransaction } from "../api"
import { QuarantinePanel } from "./QuarantinePanel"

const useLedgerTransactions = vi.hoisted(() => vi.fn())

vi.mock("../hooks/use-ledger-transactions", () => ({
  useLedgerTransactions,
}))

function makeRow(overrides: Partial<LedgerTransaction> = {}): LedgerTransaction {
  return {
    key: "txn-1",
    case_id: "case-1",
    account_id: "acct-1",
    source_document_id: "doc-1",
    ingestion_run_id: "run-1",
    statement_period_id: null,
    ref_id: "ref-1",
    row_index: 0,
    amount_minor: 123456,
    currency: "USD",
    direction: "debit",
    running_balance_minor: null,
    transaction_date: "2024-03-01",
    posted_date: null,
    value_date: null,
    effective_date: null,
    ordering_date: "2024-03-01",
    ordering_date_source: "transaction",
    description: "CARD PAYMENT",
    counterparty_raw: null,
    transaction_type: null,
    bank_reference: null,
    proof_class: "p2",
    extraction_layer: 1,
    ledger_status: "quarantined",
    quarantine_reason: "balance_break",
    superseded_by_id: null,
    ...overrides,
  }
}

/** A settled, successful query result, shaped as the panel reads it. */
function settled(transactions: LedgerTransaction[], total?: number) {
  const data: LedgerResponse = {
    case_id: "case-1",
    transactions,
    total: total ?? transactions.length,
  }
  return { data, isPending: false, isError: false, error: null }
}

beforeEach(() => {
  useLedgerTransactions.mockReset()
})

describe("QuarantinePanel and the read it asks for", () => {
  it("asks for quarantined rows and nothing else", () => {
    useLedgerTransactions.mockReturnValue(settled([]))

    render(<QuarantinePanel caseId="case-1" />)

    expect(useLedgerTransactions).toHaveBeenCalledWith("case-1", {
      ledgerStatus: "quarantined",
    })
  })

  it("keeps the caller's other filters", () => {
    useLedgerTransactions.mockReturnValue(settled([]))

    render(
      <QuarantinePanel
        caseId="case-1"
        params={{ accountId: "acct-9", startDate: "2024-01-01" }}
      />
    )

    expect(useLedgerTransactions).toHaveBeenCalledWith("case-1", {
      accountId: "acct-9",
      startDate: "2024-01-01",
      ledgerStatus: "quarantined",
    })
  })

  it("does not let a caller read some other population through this panel", () => {
    // The prop type excludes the status, so this cannot be written without a
    // cast. The runtime guarantee is worth pinning anyway: everything on this
    // screen, including the sentence about totals, is only true of quarantined
    // rows.
    useLedgerTransactions.mockReturnValue(settled([]))

    const params = { ledgerStatus: "admitted" } as never
    render(<QuarantinePanel caseId="case-1" params={params} />)

    expect(useLedgerTransactions).toHaveBeenCalledWith("case-1", {
      ledgerStatus: "quarantined",
    })
  })
})

describe("QuarantinePanel states before there are rows", () => {
  it("asks for a case rather than reading one, when none is chosen", () => {
    useLedgerTransactions.mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
    })

    render(<QuarantinePanel caseId={undefined} />)

    expect(screen.getByTestId("quarantine-no-case")).toBeTruthy()
    expect(screen.queryByTestId("quarantine-loading")).toBeNull()
    expect(screen.queryByTestId("ledger-table")).toBeNull()
  })

  it("says the read is in flight", () => {
    useLedgerTransactions.mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
    })

    render(<QuarantinePanel caseId="case-1" />)

    expect(screen.getByTestId("quarantine-loading").textContent).toContain(
      "Reading the quarantined rows"
    )
    expect(screen.queryByTestId("ledger-table")).toBeNull()
  })

  it("says a failed read is not a count of what is excluded, and shows the reason", () => {
    // A failure here is not the same failure as on the ledger panel. Nothing
    // is being counted; what is unknown is how much is being left out.
    useLedgerTransactions.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: new Error("start_date 2024-05-01 is after end_date 2024-01-01"),
    })

    render(<QuarantinePanel caseId="case-1" />)

    const failure = screen.getByTestId("quarantine-error")
    expect(failure.textContent).toContain("count of what is being excluded")
    expect(failure.textContent).toContain("is after end_date")
    expect(screen.queryByTestId("ledger-table")).toBeNull()
  })
})

describe("QuarantinePanel with no rows returned", () => {
  it("reads zero as nothing being held back, not as an absent ledger", () => {
    useLedgerTransactions.mockReturnValue(settled([]))

    render(<QuarantinePanel caseId="case-1" />)

    expect(
      screen.getByText("Nothing is being held out of this case's totals")
    ).toBeTruthy()
    expect(screen.queryByTestId("ledger-table")).toBeNull()
  })

  it("does not tell a reader that quarantined rows are outside this filter", () => {
    // The general ledger panel says exactly that, correctly, of an admitted
    // list. Repeated here it would be the opposite of what was checked.
    useLedgerTransactions.mockReturnValue(settled([]))

    render(<QuarantinePanel caseId="case-1" />)

    const description = screen.getByText(/currently quarantined/)
    expect(description.textContent).not.toContain("change the status filter")
    expect(description.textContent).toContain("superseded or rejected")
  })
})

describe("QuarantinePanel with rows", () => {
  it("counts the rows it was sent and draws them with their grounds", () => {
    useLedgerTransactions.mockReturnValue(
      settled([makeRow({ key: "a" }), makeRow({ key: "b" })])
    )

    render(<QuarantinePanel caseId="case-1" />)

    expect(screen.getByTestId("quarantine-summary").textContent).toContain(
      "2 rows held out of every total"
    )
    expect(screen.getAllByTestId("ledger-row")).toHaveLength(2)
    expect(screen.getAllByTestId("ledger-grounds-origin")).toHaveLength(2)
    expect(screen.getByText("Grounds")).toBeTruthy()
  })

  it("counts one row without calling it rows", () => {
    useLedgerTransactions.mockReturnValue(settled([makeRow()]))

    render(<QuarantinePanel caseId="case-1" />)

    expect(screen.getByTestId("quarantine-summary").textContent).toContain(
      "1 row held out of every total"
    )
  })

  it("says where a person's reasoning actually is", () => {
    // The ledger read carries the category and no detail, so without this a
    // row marked as someone's decision reads as a decision with no reason
    // given.
    useLedgerTransactions.mockReturnValue(
      settled([makeRow({ quarantine_reason: "adjudicated" })])
    )

    render(<QuarantinePanel caseId="case-1" />)

    const note = screen.getByTestId("quarantine-adjudication-note")
    expect(note.textContent).toContain("record of that decision")
    expect(note.textContent).toContain("not repeated here")
  })

  it("stays quiet when the reported total and the rows sent agree", () => {
    useLedgerTransactions.mockReturnValue(settled([makeRow()], 1))

    render(<QuarantinePanel caseId="case-1" />)

    expect(screen.queryByTestId("quarantine-count-disagreement")).toBeNull()
  })

  it("says so when more is being held back than is shown", () => {
    useLedgerTransactions.mockReturnValue(settled([makeRow()], 40))

    render(<QuarantinePanel caseId="case-1" />)

    const warning = screen.getByTestId("quarantine-count-disagreement")
    expect(warning.textContent).toContain("reported 40 quarantined rows and sent 1")
    expect(warning.textContent).toContain("More is being held out")
    expect(screen.getAllByTestId("ledger-row")).toHaveLength(1)
  })
})
