/**
 * The four states a ledger table cannot be in the middle of, and the two
 * claims this panel makes about the rows it did get.
 *
 * The hook is mocked rather than the network, because what is under test is
 * the panel's reading of a query result, not the query. `LedgerTable` is left
 * real, so a state that should not reach the table can be shown not to.
 *
 * The empty case gets the most attention here. Zero admitted rows is the
 * normal reading of this case today, and an empty state that said "no
 * transactions" would assert something the request never checked.
 */

import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { LedgerResponse, LedgerTransaction } from "../api"
import { LedgerPanel } from "./LedgerPanel"

const useLedgerTransactions = vi.hoisted(() => vi.fn())

vi.mock("../hooks/use-ledger-transactions", () => ({
  useLedgerTransactions,
}))

function makeRow(
  overrides: Partial<LedgerTransaction> = {}
): LedgerTransaction {
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
    ledger_status: "admitted",
    quarantine_reason: null,
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

describe("LedgerPanel states before there are rows", () => {
  it("asks for a case rather than reading one, when none is chosen", () => {
    useLedgerTransactions.mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
    })

    render(<LedgerPanel caseId={undefined} />)

    expect(screen.getByTestId("ledger-no-case")).toBeTruthy()
    expect(screen.queryByTestId("ledger-loading")).toBeNull()
    expect(screen.queryByTestId("ledger-table")).toBeNull()
  })

  it("says the read is in flight", () => {
    useLedgerTransactions.mockReturnValue({
      data: undefined,
      isPending: true,
      isError: false,
      error: null,
    })

    render(<LedgerPanel caseId="case-1" />)

    expect(screen.getByTestId("ledger-loading").textContent).toContain(
      "Reading the ledger"
    )
    expect(screen.queryByTestId("ledger-table")).toBeNull()
  })

  it("shows the loading failure and its reason without rendering transaction counts", () => {
    useLedgerTransactions.mockReturnValue({
      data: undefined,
      isPending: false,
      isError: true,
      error: new Error("start_date 2024-05-01 is after end_date 2024-01-01"),
    })

    render(<LedgerPanel caseId="case-1" />)

    const failure = screen.getByTestId("ledger-error")
    expect(failure.textContent).toContain("Transactions could not be loaded")
    expect(failure.textContent).toContain("is after end_date")
    expect(screen.queryByTestId("ledger-table")).toBeNull()
  })
})

describe("LedgerPanel with no rows returned", () => {
  it("names the status it filtered on, and says the rest are uncounted", () => {
    useLedgerTransactions.mockReturnValue(settled([]))

    render(<LedgerPanel caseId="case-1" />)

    expect(screen.getByText("No admitted rows in the ledger")).toBeTruthy()
    const description = screen.getByText(/status "admitted"/)
    expect(description.textContent).toContain("quarantined")
    expect(description.textContent).toContain("not counted here")
    expect(screen.queryByTestId("ledger-table")).toBeNull()
  })

  it("names the status actually asked for when it is not the default", () => {
    useLedgerTransactions.mockReturnValue(settled([]))

    render(
      <LedgerPanel caseId="case-1" params={{ ledgerStatus: "quarantined" }} />
    )

    expect(screen.getByText("No quarantined rows in the ledger")).toBeTruthy()
  })

  it("passes the case and params straight through to the hook", () => {
    useLedgerTransactions.mockReturnValue(settled([]))
    const params = { ledgerStatus: "rejected" } as const

    render(<LedgerPanel caseId="case-1" params={params} />)

    expect(useLedgerTransactions).toHaveBeenCalledWith("case-1", params)
  })
})

describe("LedgerPanel with rows", () => {
  it("counts the rows it was sent and renders them", () => {
    useLedgerTransactions.mockReturnValue(
      settled([makeRow({ key: "a" }), makeRow({ key: "b" })])
    )

    render(<LedgerPanel caseId="case-1" />)

    expect(screen.getByTestId("ledger-summary").textContent).toBe(
      "2 rows, admitted."
    )
    expect(screen.getAllByTestId("ledger-row")).toHaveLength(2)
  })

  it("counts one row without calling it rows", () => {
    useLedgerTransactions.mockReturnValue(settled([makeRow()]))

    render(<LedgerPanel caseId="case-1" />)

    expect(screen.getByTestId("ledger-summary").textContent).toBe(
      "1 row, admitted."
    )
  })

  it("stays quiet when the reported total and the rows sent agree", () => {
    useLedgerTransactions.mockReturnValue(settled([makeRow()], 1))

    render(<LedgerPanel caseId="case-1" />)

    expect(screen.queryByTestId("ledger-count-disagreement")).toBeNull()
  })

  it("says so when the reported total and the rows sent disagree", () => {
    useLedgerTransactions.mockReturnValue(settled([makeRow()], 40))

    render(<LedgerPanel caseId="case-1" />)

    const warning = screen.getByTestId("ledger-count-disagreement")
    expect(warning.textContent).toContain("reported 40 rows and sent 1")
    expect(warning.textContent).toContain("not all of it")
    expect(screen.getAllByTestId("ledger-row")).toHaveLength(1)
  })
})

describe("LedgerPanel filtered and incomplete empty answers", () => {
  it.each([
    { accountId: "acct-2" },
    { startDate: "2026-02-01" },
    { endDate: "2026-02-28" },
  ])("limits an empty answer to the requested scope %o", (params) => {
    useLedgerTransactions.mockReturnValue(settled([]))
    render(<LedgerPanel caseId="case-1" params={params} />)
    expect(
      screen.getByText("No admitted rows match these filters")
    ).toBeTruthy()
    expect(screen.queryByText("No admitted rows in the ledger")).toBeNull()
    expect(
      screen.getByText(/does not establish that no transactions occurred/)
    ).toBeTruthy()
    expect(screen.getByTestId("ledger-filter-scope").textContent).toContain(
      Object.values(params)[0]
    )
  })

  it("retains a response count disagreement even when no rows arrived", () => {
    useLedgerTransactions.mockReturnValue(settled([], 40))
    render(<LedgerPanel caseId="case-1" />)
    expect(
      screen.getByTestId("ledger-count-disagreement").textContent
    ).toContain("reported 40 rows and sent 0")
    expect(screen.queryByTestId("ledger-table")).toBeNull()
  })

  it("shows both date bounds and account scope beside populated results", () => {
    useLedgerTransactions.mockReturnValue(settled([makeRow()]))
    render(
      <LedgerPanel
        caseId="case-1"
        params={{
          accountId: "acct-1",
          startDate: "2024-01-01",
          endDate: "2024-12-31",
        }}
      />
    )
    const scope = screen.getByTestId("ledger-filter-scope").textContent
    expect(scope).toContain("acct-1")
    expect(scope).toContain("on or after 2024-01-01")
    expect(scope).toContain("on or before 2024-12-31")
    expect(scope).toContain("may differ")
    expect(screen.getAllByTestId("ledger-row")).toHaveLength(1)
  })
})
