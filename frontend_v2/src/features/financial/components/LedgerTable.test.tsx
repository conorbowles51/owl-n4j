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

import { fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

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

describe("LedgerTable grounds column", () => {
  it("does not draw the column unless asked", () => {
    // A mixed list is not about quarantine, and a mostly-empty column headed
    // "Grounds" beside a list of admitted rows suggests the question was asked
    // of each of them.
    render(
      <LedgerTable
        transactions={[
          makeRow({ ledger_status: "quarantined", quarantine_reason: "balance_break" }),
        ]}
      />
    )
    expect(screen.queryByText("Grounds")).toBeNull()
    expect(screen.queryByTestId("ledger-grounds-origin")).toBeNull()
  })

  it("moves the reason out of the status cell rather than showing it twice", () => {
    // Same badge, one position or the other. Two copies of it would be two
    // things to keep in step within a single row.
    render(
      <LedgerTable
        showQuarantineGrounds
        transactions={[
          makeRow({ ledger_status: "quarantined", quarantine_reason: "balance_break" }),
        ]}
      />
    )
    expect(screen.getAllByTestId("ledger-quarantine-reason")).toHaveLength(1)
    const status = screen.getByTestId("ledger-status")
    expect(status.parentElement?.textContent).not.toContain("Balance break")
  })

  it("keeps the status column, so a row that is not quarantined still shows", () => {
    // The list is filtered to quarantined rows, so the status badge is
    // constant and looks redundant. It is not: a row arriving with some other
    // status is the thing a reader most needs to see, and replacing the column
    // with the grounds would hide exactly that.
    render(
      <LedgerTable
        showQuarantineGrounds
        transactions={[
          makeRow({ ledger_status: "superseded", quarantine_reason: "adjudicated" }),
        ]}
      />
    )
    expect(screen.getByTestId("ledger-status").textContent).toContain("Superseded")
    expect(screen.getByTestId("ledger-quarantine-reason").textContent).toContain(
      "Set aside by a person"
    )
  })

  it("separates a person's decision from the ledger's own checks", () => {
    render(
      <LedgerTable
        showQuarantineGrounds
        transactions={[
          makeRow({ key: "a", quarantine_reason: "adjudicated" }),
          makeRow({ key: "b", quarantine_reason: "balance_break" }),
        ]}
      />
    )
    const [person, check] = screen.getAllByTestId("ledger-grounds-origin")
    expect(person.getAttribute("data-decided-by-person")).toBe("true")
    expect(person.textContent).toContain("Decided by a person")
    expect(check.getAttribute("data-decided-by-person")).toBe("false")
    expect(check.textContent).toContain("Established by a check")
  })

  it("will not call an unreadable reason a machine check", () => {
    // Three-valued on the screen as well as in the reader. "false" here would
    // tell a reader the arithmetic established grounds this build cannot even
    // name.
    render(
      <LedgerTable
        showQuarantineGrounds
        transactions={[makeRow({ quarantine_reason: "embargoed" })]}
      />
    )
    expect(
      screen.getByTestId("ledger-grounds-origin").getAttribute("data-decided-by-person")
    ).toBe("unknown")
    expect(
      screen.getByTestId("ledger-quarantine-reason").getAttribute("data-unrecognised")
    ).toBe("true")
  })

  it("states an absent reason rather than leaving the cell empty", () => {
    // An empty cell under "Grounds" reads as "none needed", which is the
    // opposite of what a quarantined row with no recorded reason means.
    render(
      <LedgerTable
        showQuarantineGrounds
        transactions={[
          makeRow({ ledger_status: "quarantined", quarantine_reason: null }),
        ]}
      />
    )
    expect(screen.getByTestId("ledger-no-grounds").textContent).toBe(
      "No grounds recorded"
    )
    expect(screen.queryByTestId("ledger-quarantine-reason")).toBeNull()
  })

  it("spans the empty sentence across the column it added", () => {
    // The colSpan is computed rather than fixed. Left at seven it would leave
    // a stray cell beside the sentence.
    render(<LedgerTable showQuarantineGrounds transactions={[]} />)
    expect(screen.getByTestId("ledger-table-empty").getAttribute("colspan")).toBe("8")

    render(<LedgerTable transactions={[]} />)
    expect(
      screen.getAllByTestId("ledger-table-empty")[1].getAttribute("colspan")
    ).toBe("7")
  })
})

/**
 * The action column: what it offers, and the one case where it offers nothing
 * and has to say so.
 *
 * Nothing here changes a row. The table hands the row back and stops, which is
 * what keeps every case above testable against rows alone, so what these pin is
 * which change was offered on which row and that the row handed back is the one
 * whose button was pressed.
 */
describe("LedgerTable action column", () => {
  it("does not draw the column unless a caller can act on it", () => {
    // A column of buttons that do nothing is worse than no column: it says a
    // change can be asked for from a screen that cannot ask for one.
    render(<LedgerTable transactions={[makeRow()]} />)
    expect(screen.queryByText("Decision")).toBeNull()
    expect(screen.queryByTestId("ledger-row-action")).toBeNull()
    expect(screen.queryByTestId("ledger-no-action")).toBeNull()
  })

  it("offers a setting aside on a row that is counting toward totals", () => {
    render(
      <LedgerTable
        transactions={[makeRow({ ledger_status: "admitted" })]}
        onAdjudicate={vi.fn()}
      />
    )
    const button = screen.getByTestId("ledger-row-action")
    expect(button.getAttribute("data-change")).toBe("quarantine")
    expect(button.textContent).toBe("Set aside")
  })

  it("offers a release on a row that is being held out", () => {
    render(
      <LedgerTable
        showQuarantineGrounds
        transactions={[
          makeRow({ ledger_status: "quarantined", quarantine_reason: "balance_break" }),
        ]}
        onAdjudicate={vi.fn()}
      />
    )
    const button = screen.getByTestId("ledger-row-action")
    expect(button.getAttribute("data-change")).toBe("release")
    expect(button.textContent).toBe("Let back in")
  })

  it("offers a change per row, decided by that row's own status", () => {
    // Two rows in one list, and the list being filtered to one status is not
    // something this component may assume: `QuarantinePanel` reads a filter the
    // backend applied, and a row arriving with another status is exactly the
    // case the status column is kept for.
    render(
      <LedgerTable
        transactions={[
          makeRow({ key: "a", ledger_status: "admitted" }),
          makeRow({ key: "b", ledger_status: "quarantined" }),
        ]}
        onAdjudicate={vi.fn()}
      />
    )
    expect(
      screen.getAllByTestId("ledger-row-action").map((b) => b.getAttribute("data-change"))
    ).toEqual(["quarantine", "release"])
  })

  it("hands back the row whose button was pressed, and does nothing else", () => {
    const onAdjudicate = vi.fn()
    render(
      <LedgerTable
        transactions={[makeRow({ key: "a" }), makeRow({ key: "b" })]}
        onAdjudicate={onAdjudicate}
      />
    )

    fireEvent.click(screen.getAllByTestId("ledger-row-action")[1])

    expect(onAdjudicate).toHaveBeenCalledTimes(1)
    expect(onAdjudicate.mock.calls[0][0].key).toBe("b")
  })

  it("says it cannot read the status rather than leaving the cell blank", () => {
    // The one row on the screen that most needs explaining. An empty cell in a
    // column of buttons reads as "nothing can be done to this row", when what
    // is true is that this build cannot tell which change it would be -- and
    // therefore cannot tell whether the row is counting toward the totals.
    render(
      <LedgerTable
        transactions={[makeRow({ ledger_status: "escheated" })]}
        onAdjudicate={vi.fn()}
      />
    )
    expect(screen.queryByTestId("ledger-row-action")).toBeNull()
    expect(screen.getByTestId("ledger-no-action").textContent).toBe(
      "Status unread, no change offered"
    )
  })

  it("spans the empty sentence across this column too", () => {
    render(<LedgerTable transactions={[]} onAdjudicate={vi.fn()} />)
    expect(screen.getByTestId("ledger-table-empty").getAttribute("colspan")).toBe("8")

    render(
      <LedgerTable showQuarantineGrounds transactions={[]} onAdjudicate={vi.fn()} />
    )
    expect(
      screen.getAllByTestId("ledger-table-empty")[1].getAttribute("colspan")
    ).toBe("9")
  })
})
