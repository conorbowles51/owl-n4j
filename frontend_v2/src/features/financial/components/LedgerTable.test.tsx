/**
 * What this component has to get right about a ledger row.
 *
 * These are not tests that the formatter and the narrowers work — they have
 * their own suite in `lib/ledger-format.test.ts`. They are tests that this
 * component routes every value through them, and that the three cases which
 * mislead silently when got wrong are visible on the screen: an amount that
 * could not be scaled, a running balance that is absent, and a vocabulary
 * member this build cannot read.
 *
 * Each of those fails quietly rather than loudly if the component regresses,
 * which is the reason to pin them here rather than trust a reading of the
 * markup.
 */

import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import type { LedgerTransaction } from "../api"
import { LedgerTable } from "./LedgerTable"

/**
 * A row carrying every field `TransactionView.to_json` emits, so a test that
 * overrides one field is changing exactly one thing.
 */
function makeRow(overrides: Partial<LedgerTransaction> = {}): LedgerTransaction {
  return {
    key: "txn-1",
    case_id: "case-1",
    account_id: "acct-1",
    source_document_id: "doc-1",
    ingestion_run_id: "run-1",
    statement_period_id: "period-1",
    ref_id: "ref-1",
    row_index: 0,
    amount_minor: 123456,
    currency: "USD",
    direction: "debit",
    running_balance_minor: null,
    transaction_date: "2024-03-01",
    posted_date: "2024-03-02",
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

describe("LedgerTable money", () => {
  it("scales by the row's own currency rather than by a hundred", () => {
    render(
      <LedgerTable
        transactions={[
          makeRow({ key: "usd", amount_minor: 123456, currency: "USD" }),
          makeRow({ key: "jpy", amount_minor: 123456, currency: "JPY" }),
        ]}
      />
    )

    const amounts = screen.getAllByTestId("ledger-amount")
    expect(amounts[0].textContent).toBe("1,234.56")
    expect(amounts[1].textContent).toBe("123,456")
  })

  it("shows the currency code beside the figure", () => {
    render(<LedgerTable transactions={[makeRow({ currency: "gbp" })]} />)
    expect(screen.getByTestId("ledger-row").textContent).toContain("GBP")
  })

  it("marks an amount it could not scale, rather than passing it off as a figure", () => {
    render(<LedgerTable transactions={[makeRow({ amount_minor: 1234.5 })]} />)
    expect(screen.getByTestId("ledger-amount-unscaled")).toBeTruthy()
    expect(screen.getByTestId("ledger-amount").textContent).toBe("1234.5")
  })

  it("adds no marker when the amount scaled cleanly", () => {
    render(<LedgerTable transactions={[makeRow()]} />)
    expect(screen.queryByTestId("ledger-amount-unscaled")).toBeNull()
  })
})

describe("LedgerTable running balance", () => {
  it("states an absent running balance instead of leaving the cell blank", () => {
    render(<LedgerTable transactions={[makeRow({ running_balance_minor: null })]} />)
    const absence = screen.getByTestId("ledger-no-balance")
    expect(absence.textContent).toBe("No running balance")
    expect(screen.queryByTestId("ledger-balance")).toBeNull()
  })

  it("renders a balance that is present, keeping a negative sign", () => {
    render(
      <LedgerTable
        transactions={[makeRow({ running_balance_minor: -50000, currency: "USD" })]}
      />
    )
    expect(screen.getByTestId("ledger-balance").textContent).toBe("-500.00")
    expect(screen.queryByTestId("ledger-no-balance")).toBeNull()
  })
})

describe("LedgerTable closed vocabularies", () => {
  it("renders every known member through its narrowed label", () => {
    render(
      <LedgerTable
        transactions={[
          makeRow({
            direction: "credit",
            ledger_status: "quarantined",
            quarantine_reason: "balance_break",
            proof_class: "p0",
            extraction_layer: 0,
            ordering_date_source: "posted",
          }),
        ]}
      />
    )

    expect(screen.getByTestId("ledger-direction").textContent).toBe("Credit")
    expect(screen.getByTestId("ledger-status").textContent).toBe("Quarantined")
    expect(screen.getByTestId("ledger-quarantine-reason").textContent).toBe(
      "Balance break"
    )
    expect(screen.getByTestId("ledger-proof-class").textContent).toBe("P0")
    expect(screen.getByTestId("ledger-extraction-layer").textContent).toBe("Native")
    expect(screen.getByTestId("ledger-date-source").textContent).toBe("Posted date")
  })

  it("marks every known member as recognised", () => {
    render(<LedgerTable transactions={[makeRow()]} />)
    for (const testId of [
      "ledger-direction",
      "ledger-status",
      "ledger-proof-class",
      "ledger-extraction-layer",
      "ledger-date-source",
    ]) {
      expect(screen.getByTestId(testId).getAttribute("data-unrecognised")).toBe(
        "false"
      )
    }
  })

  it("shows a status this build cannot read, with the raw value in it", () => {
    render(<LedgerTable transactions={[makeRow({ ledger_status: "escheated" })]} />)
    const badge = screen.getByTestId("ledger-status")
    expect(badge.getAttribute("data-unrecognised")).toBe("true")
    expect(badge.textContent).toContain("escheated")
    expect(badge.textContent).toContain("Unrecognised")
  })

  it("shows an unreadable direction, proof class and date source the same way", () => {
    render(
      <LedgerTable
        transactions={[
          makeRow({
            direction: "reversal",
            proof_class: "p9",
            ordering_date_source: "booking",
          }),
        ]}
      />
    )

    for (const [testId, raw] of [
      ["ledger-direction", "reversal"],
      ["ledger-proof-class", "p9"],
      ["ledger-date-source", "booking"],
    ] as const) {
      const badge = screen.getByTestId(testId)
      expect(badge.getAttribute("data-unrecognised")).toBe("true")
      expect(badge.textContent).toContain(raw)
    }
  })

  it("shows an extraction layer outside the range this build knows", () => {
    render(<LedgerTable transactions={[makeRow({ extraction_layer: 7 })]} />)
    const badge = screen.getByTestId("ledger-extraction-layer")
    expect(badge.getAttribute("data-unrecognised")).toBe("true")
    expect(badge.textContent).toContain("7")
  })

  it("marks the grounded-model layer as the fallback it is", () => {
    render(<LedgerTable transactions={[makeRow({ extraction_layer: 3 })]} />)
    const badge = screen.getByTestId("ledger-extraction-layer")
    expect(badge.getAttribute("data-fallback")).toBe("true")
    expect(badge.textContent).toBe("Grounded model")
  })

  it("does not mark a normal extraction layer as the fallback", () => {
    render(<LedgerTable transactions={[makeRow({ extraction_layer: 2 })]} />)
    expect(
      screen.getByTestId("ledger-extraction-layer").getAttribute("data-fallback")
    ).toBe("false")
  })

  it("carries the narrowed description as the badge's own explanation", () => {
    render(<LedgerTable transactions={[makeRow({ ledger_status: "admitted" })]} />)
    expect(screen.getByTestId("ledger-status").getAttribute("title")).toContain(
      "Counts toward totals"
    )
  })
})

describe("LedgerTable row detail", () => {
  it("shows no quarantine reason when the row carries none", () => {
    render(<LedgerTable transactions={[makeRow({ quarantine_reason: null })]} />)
    expect(screen.queryByTestId("ledger-quarantine-reason")).toBeNull()
  })

  it("says a superseded row was replaced, and says nothing when it was not", () => {
    const { unmount } = render(
      <LedgerTable
        transactions={[
          makeRow({ ledger_status: "superseded", superseded_by_id: "txn-2" }),
        ]}
      />
    )
    expect(screen.getByTestId("ledger-superseded-by").textContent).toBe(
      "Replaced by a later row"
    )
    unmount()

    render(<LedgerTable transactions={[makeRow()]} />)
    expect(screen.queryByTestId("ledger-superseded-by")).toBeNull()
  })

  it("states an absent description rather than leaving the cell blank", () => {
    render(<LedgerTable transactions={[makeRow({ description: null })]} />)
    expect(screen.getByTestId("ledger-no-description").textContent).toBe(
      "No description recorded"
    )
  })

  it("shows counterparty and bank reference only when the row carries them", () => {
    const { unmount } = render(<LedgerTable transactions={[makeRow()]} />)
    expect(screen.queryByTestId("ledger-counterparty")).toBeNull()
    expect(screen.queryByTestId("ledger-bank-reference")).toBeNull()
    unmount()

    render(
      <LedgerTable
        transactions={[
          makeRow({ counterparty_raw: "ACME LTD", bank_reference: "BR-99" }),
        ]}
      />
    )
    expect(screen.getByTestId("ledger-counterparty").textContent).toBe("ACME LTD")
    expect(screen.getByTestId("ledger-bank-reference").textContent).toBe("BR-99")
  })

  it("shows the ordering date, which is the one the ledger reconciles by", () => {
    render(
      <LedgerTable
        transactions={[
          makeRow({ ordering_date: "2024-03-01", posted_date: "2024-03-09" }),
        ]}
      />
    )
    const row = screen.getByTestId("ledger-row")
    expect(within(row).getByText("2024-03-01")).toBeTruthy()
    expect(row.textContent).not.toContain("2024-03-09")
  })
})

describe("LedgerTable ordering and emptiness", () => {
  it("draws rows in the order given, rather than sorting them itself", () => {
    render(
      <LedgerTable
        transactions={[
          makeRow({ key: "b", ordering_date: "2024-05-01" }),
          makeRow({ key: "a", ordering_date: "2024-01-01" }),
        ]}
      />
    )
    const keys = screen
      .getAllByTestId("ledger-row")
      .map((row) => row.getAttribute("data-row-key"))
    expect(keys).toEqual(["b", "a"])
  })

  it("says so rather than showing a header over nothing", () => {
    render(<LedgerTable transactions={[]} />)
    expect(screen.getByTestId("ledger-table-empty").textContent).toBe(
      "No ledger rows to show."
    )
    expect(screen.queryAllByTestId("ledger-row")).toHaveLength(0)
  })
})
