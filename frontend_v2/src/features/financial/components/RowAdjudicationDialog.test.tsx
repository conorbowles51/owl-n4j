/**
 * What this dialog has to get right about changing a row's standing.
 *
 * The reader underneath has its own suite in `lib/adjudication-format.test.ts`
 * and the mutation has one in `hooks/use-row-adjudication.test.tsx`. Nothing
 * here re-checks either. What is checked is the four things this layer decides
 * for itself, each of which is wrong in a way that looks fine on screen.
 *
 * **Which change is offered comes off the row.** Offering "set aside" for a row
 * already held, or "let back in" for one that was never held, sends a write
 * whose only possible answer is "nothing to do" while having told the person a
 * different question was being asked. A status this build cannot read offers
 * neither, because the verb is derived from the status and there is nothing to
 * derive it from.
 *
 * **A blank reason is refused before it is sent.** Four writers underneath
 * refuse one, and three of them refuse it with an ordinary 200, so a blank
 * reason that gets sent comes back looking like a considered answer. The guard
 * here is `trim`, which is at least as strict as the check constraint on the
 * table and never looser.
 *
 * **A refusal is not an error.** Four of the six outcomes arrive with a 200 and
 * only two of them moved anything, so the sentence about whether the row moved
 * is asserted here against `applied` for outcomes that succeeded and outcomes
 * that did not.
 *
 * **The statement-balance fact is said here or nowhere.** It is deliberately
 * not written to the record, so a dialog that drops it has lost it. `false` and
 * `null` say different things and both are asserted, separately.
 *
 * The api object is spied on rather than the module mocked, following
 * `SendToLedgerDialog.test.tsx`. `vi.mock("../api")` would also blank the
 * closed vocabularies the format readers import from it, and every value in
 * every test would then narrow to "unrecognised" while the tests still looked
 * like they were exercising the real thing.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { financialAPI, type LedgerTransaction, type RowAdjudication } from "../api"
import { RowAdjudicationDialog } from "./RowAdjudicationDialog"

const CASE_ID = "case-1"

/**
 * A row carrying every field `TransactionView.to_json` emits, so a test that
 * overrides one field is changing exactly one thing. Same shape as the fixture
 * in `LedgerTable.test.tsx`, and admitted by default because that is the row
 * the "set aside" path starts from.
 */
function makeRow(overrides: Partial<LedgerTransaction> = {}): LedgerTransaction {
  return {
    key: "txn-1",
    case_id: CASE_ID,
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

/** A successful quarantine, with the fields a given test does not care about filled in. */
function answer(overrides: Partial<RowAdjudication> = {}): RowAdjudication {
  return {
    transaction_id: "txn-1",
    outcome: "quarantined",
    applied: true,
    reason: null,
    ledger_status: "quarantined",
    quarantine_reason: "adjudicated",
    adjudication_id: "adj-1",
    rescues_period: false,
    ...overrides,
  }
}

/**
 * `caseId` arrives as an options key rather than as a second positional
 * argument with a default, because a defaulted parameter cannot express "no
 * case is open": passing `undefined` to one takes the default, so the test for
 * that case would silently run with a case open and pass on the wrong grounds.
 */
function renderDialog(
  row: LedgerTransaction = makeRow(),
  options: { caseId?: string | undefined } = {}
) {
  const caseId = "caseId" in options ? options.caseId : CASE_ID
  const onClose = vi.fn()
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RowAdjudicationDialog caseId={caseId} row={row} open onClose={onClose} />
    </QueryClientProvider>
  )
  return { ...view, onClose, queryClient }
}

/** Type grounds into the box, which is the minimum the dialog will send on. */
function giveGrounds(text = "Duplicate of row 44.") {
  fireEvent.change(screen.getByTestId("adjudication-reason-input"), {
    target: { value: text },
  })
}

function submitButton(): HTMLButtonElement {
  return screen.getByTestId("adjudication-submit") as HTMLButtonElement
}

beforeEach(() => {
  vi.restoreAllMocks()
})

/* ------------------------------------------------------------------ *
 * Which change is offered
 * ------------------------------------------------------------------ */

describe("RowAdjudicationDialog: which change it offers", () => {
  it("offers setting aside for a row that is in the totals", () => {
    renderDialog(makeRow({ ledger_status: "admitted" }))
    expect(screen.getByTestId("adjudication-title").textContent).toBe(
      "Set this row aside"
    )
    expect(submitButton().textContent).toContain("Set aside")
  })

  it("offers letting back in for a row that is already held", () => {
    renderDialog(makeRow({ ledger_status: "quarantined", quarantine_reason: "adjudicated" }))
    expect(screen.getByTestId("adjudication-title").textContent).toBe(
      "Let this row back in"
    )
    expect(submitButton().textContent).toContain("Let back in")
  })

  it("sends a held row to the release route and any other row to the quarantine route", async () => {
    // The verb is derived from the row rather than passed in, so this is the
    // whole of what decides which of the two writes happens. Getting it
    // backwards puts a row back into the totals when somebody asked for it to
    // be taken out.
    const release = vi.spyOn(financialAPI, "releaseRow").mockResolvedValue(
      answer({ outcome: "released", ledger_status: "admitted", quarantine_reason: null })
    )
    const quarantine = vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(answer())

    const held = renderDialog(makeRow({ ledger_status: "quarantined" }))
    giveGrounds("Confirmed against the original statement.")
    fireEvent.click(submitButton())
    await waitFor(() => expect(release).toHaveBeenCalledTimes(1))
    expect(quarantine).not.toHaveBeenCalled()
    held.unmount()

    renderDialog(makeRow({ ledger_status: "admitted" }))
    giveGrounds()
    fireEvent.click(submitButton())
    await waitFor(() => expect(quarantine).toHaveBeenCalledTimes(1))
    expect(release).toHaveBeenCalledTimes(1)
  })

  it("offers no change at all for a status this build cannot read", () => {
    // Not a refusal on the ledger's behalf. The change to offer is derived from
    // the status, so an unreadable status leaves nothing to derive it from, and
    // guessing would send a write nobody asked for.
    renderDialog(makeRow({ ledger_status: "squelched" }))
    expect(screen.queryByTestId("adjudication-submit")).toBeNull()
    expect(screen.queryByTestId("adjudication-reason-input")).toBeNull()
  })

  it("still names the row and shows the status it could not read", () => {
    renderDialog(makeRow({ ledger_status: "squelched" }))
    const status = screen.getByTestId("adjudication-current-status")
    expect(status.getAttribute("data-unrecognised")).toBe("true")
    expect(status.textContent).toContain("squelched")
    expect(screen.getByTestId("adjudication-row")).toBeTruthy()
  })

  it("does not screen out a row the ledger will refuse", () => {
    // A superseded row is offered the write and the ledger's own refusal is
    // what the person is shown. A second copy of the ledger's rules in the
    // browser is a second thing to keep in step, and the copy is what drifts.
    renderDialog(makeRow({ ledger_status: "superseded" }))
    expect(submitButton()).toBeTruthy()
  })
})

/* ------------------------------------------------------------------ *
 * The grounds are required
 * ------------------------------------------------------------------ */

describe("RowAdjudicationDialog: the grounds", () => {
  it("will not send with the box empty", () => {
    const write = vi.spyOn(financialAPI, "quarantineRow")
    renderDialog()
    expect(submitButton().disabled).toBe(true)
    fireEvent.click(submitButton())
    expect(write).not.toHaveBeenCalled()
  })

  it("will not send on whitespace alone", () => {
    // The check constraint on the table treats tabs, returns and newlines as
    // blank, and the writers above it refuse a blank with an ordinary 200. So
    // whitespace sent from here comes back as a considered-looking answer that
    // did nothing.
    const write = vi.spyOn(financialAPI, "quarantineRow")
    renderDialog()
    giveGrounds("  \t\r\n  ")
    expect(submitButton().disabled).toBe(true)
    fireEvent.click(submitButton())
    expect(write).not.toHaveBeenCalled()
  })

  it("sends once there are words, and sends them trimmed", async () => {
    // Trimmed because the writer stores `"<actor>: <reason.strip()>"` either
    // way, so the words that go on the record are the words the guard checked.
    const write = vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(answer())
    renderDialog()
    giveGrounds("  Duplicate of row 44.\n")
    expect(submitButton().disabled).toBe(false)
    fireEvent.click(submitButton())

    await waitFor(() => expect(write).toHaveBeenCalledTimes(1))
    expect(write).toHaveBeenCalledWith({
      caseId: CASE_ID,
      transactionId: "txn-1",
      reason: "Duplicate of row 44.",
    })
  })

  it("sends the row's own key as the transaction", async () => {
    // `TransactionView.to_view` sets `key` to the row's id, and the route takes
    // that id in its path. Anything else here addresses the write to a row that
    // does not exist and gets a 404 the person cannot act on.
    const write = vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(answer())
    renderDialog(makeRow({ key: "9f1c2b4e-0000-4000-8000-000000000001" }))
    giveGrounds()
    fireEvent.click(submitButton())

    await waitFor(() => expect(write).toHaveBeenCalledTimes(1))
    expect(write.mock.calls[0][0].transactionId).toBe(
      "9f1c2b4e-0000-4000-8000-000000000001"
    )
  })
})

/* ------------------------------------------------------------------ *
 * What the answer is allowed to say
 * ------------------------------------------------------------------ */

describe("RowAdjudicationDialog: the answer", () => {
  it("reports movement from applied when the row was taken out", async () => {
    vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(answer({ applied: true }))
    renderDialog()
    giveGrounds()
    fireEvent.click(submitButton())

    const shown = await screen.findByTestId("adjudication-answer")
    expect(shown.getAttribute("data-applied")).toBe("true")
    expect(screen.getByTestId("adjudication-moved").textContent).toBe(
      "This row's standing changed."
    )
  })

  it("shows a refusal as an answer rather than as a failure", async () => {
    // A refusal is a 200 carrying the refusal, so React Query reports success.
    // A screen wired to that tells somebody a row left the totals when the
    // ledger declined to take it out.
    vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(
      answer({
        outcome: "refused",
        applied: false,
        reason: "This row belongs to a period that has been reconciled.",
        ledger_status: "admitted",
        quarantine_reason: null,
        adjudication_id: null,
        rescues_period: null,
      })
    )
    renderDialog()
    giveGrounds()
    fireEvent.click(submitButton())

    const shown = await screen.findByTestId("adjudication-answer")
    expect(shown.getAttribute("data-outcome")).toBe("refused")
    expect(shown.getAttribute("data-applied")).toBe("false")
    expect(screen.getByTestId("adjudication-moved").textContent).toBe(
      "Nothing about this row changed."
    )
    expect(screen.queryByTestId("adjudication-error")).toBeNull()
  })

  it("says nothing moved when applied says so, whatever the outcome word says", async () => {
    // The two are derived from each other on a backend of one version, so a
    // disagreement means this build and that one do not mean the same thing by
    // a word. What the person is told about the row comes from `applied`.
    vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(
      answer({ outcome: "quarantined", applied: false })
    )
    renderDialog()
    giveGrounds()
    fireEvent.click(submitButton())

    await screen.findByTestId("adjudication-answer")
    expect(screen.getByTestId("adjudication-moved").textContent).toBe(
      "Nothing about this row changed."
    )
    expect(screen.getByTestId("adjudication-disagreement")).toBeTruthy()
  })

  it("raises no contradiction when the two agree", async () => {
    vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(answer({ applied: true }))
    renderDialog()
    giveGrounds()
    fireEvent.click(submitButton())

    await screen.findByTestId("adjudication-answer")
    expect(screen.queryByTestId("adjudication-disagreement")).toBeNull()
  })

  it("names where the row now stands and on whose grounds", async () => {
    vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(answer())
    renderDialog()
    giveGrounds()
    fireEvent.click(submitButton())

    await screen.findByTestId("adjudication-answer")
    expect(screen.getByTestId("adjudication-status-now").textContent).toContain("Quarantined")
    // Grounds are a proof or a person and the two must not look alike, so the
    // grounds the row now carries are shown rather than assumed.
    expect(screen.getByTestId("adjudication-grounds")).toBeTruthy()
    expect(screen.getByTestId("adjudication-record-id").textContent).toContain("adj-1")
  })
})

/* ------------------------------------------------------------------ *
 * Whose words the reason field holds
 * ------------------------------------------------------------------ */

describe("RowAdjudicationDialog: the reason field in the answer", () => {
  it("puts the note about whose wording it is beside the wording", async () => {
    // The field is never the person's own words on any outcome. Shown without
    // that note it reads back as somebody's stated grounds, which is the one
    // thing an evidence log cannot do.
    vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(
      answer({ reason: "Removing this row balances the statement." })
    )
    renderDialog()
    giveGrounds()
    fireEvent.click(submitButton())

    await screen.findByTestId("adjudication-answer")
    expect(screen.getByTestId("adjudication-reason").getAttribute("data-reason-kind")).toBe(
      "rescue-note"
    )
    expect(screen.getByTestId("adjudication-reason-provenance")).toBeTruthy()
  })

  it("keeps the heading and drops the note when the field carries nothing", async () => {
    // A release carries no text here by design: the words the person gave went
    // onto the record. The heading says that; there is nothing to attribute.
    vi.spyOn(financialAPI, "releaseRow").mockResolvedValue(
      answer({
        outcome: "released",
        reason: null,
        ledger_status: "admitted",
        quarantine_reason: null,
        rescues_period: null,
      })
    )
    renderDialog(makeRow({ ledger_status: "quarantined" }))
    giveGrounds("Confirmed against the original statement.")
    fireEvent.click(submitButton())

    await screen.findByTestId("adjudication-answer")
    expect(screen.getByTestId("adjudication-reason").getAttribute("data-reason-kind")).toBe(
      "not-carried"
    )
    expect(screen.queryByTestId("adjudication-reason-provenance")).toBeNull()
  })
})

/* ------------------------------------------------------------------ *
 * The statement check, which is said here or nowhere
 * ------------------------------------------------------------------ */

describe("RowAdjudicationDialog: whether the statement balanced", () => {
  it("says so when taking the row out closed the gap", async () => {
    vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(
      answer({ rescues_period: true })
    )
    renderDialog()
    giveGrounds()
    fireEvent.click(submitButton())

    await screen.findByTestId("adjudication-answer")
    const rescue = screen.getByTestId("adjudication-rescue")
    expect(rescue.getAttribute("data-rescue-key")).toBe("rescue-balanced")
    expect(rescue.getAttribute("data-rescue-raw")).toBe("true")
  })

  it("distinguishes no gap closed from the question not being answerable", async () => {
    // `false` and `null` are two facts, not one. One says no gap was closed;
    // the other says nothing was established either way. Rendered alike, the
    // second reads as the first.
    vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(
      answer({ rescues_period: false })
    )
    const none = renderDialog()
    giveGrounds()
    fireEvent.click(submitButton())
    await screen.findByTestId("adjudication-answer")
    expect(screen.getByTestId("adjudication-rescue").getAttribute("data-rescue-key")).toBe(
      "rescue-none"
    )
    expect(screen.getByTestId("adjudication-rescue").getAttribute("data-rescue-raw")).toBe(
      "false"
    )
    none.unmount()

    vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(
      answer({ rescues_period: null })
    )
    renderDialog()
    giveGrounds()
    fireEvent.click(submitButton())
    await screen.findByTestId("adjudication-answer")
    expect(screen.getByTestId("adjudication-rescue").getAttribute("data-rescue-key")).toBe(
      "rescue-unknown"
    )
    expect(screen.getByTestId("adjudication-rescue").getAttribute("data-rescue-raw")).toBe(
      "null"
    )
  })

  it("says nothing about a statement where no removal was checked against one", async () => {
    vi.spyOn(financialAPI, "releaseRow").mockResolvedValue(
      answer({
        outcome: "released",
        ledger_status: "admitted",
        quarantine_reason: null,
        rescues_period: null,
      })
    )
    renderDialog(makeRow({ ledger_status: "quarantined" }))
    giveGrounds("Confirmed against the original statement.")
    fireEvent.click(submitButton())

    await screen.findByTestId("adjudication-answer")
    expect(screen.queryByTestId("adjudication-rescue")).toBeNull()
  })
})

/* ------------------------------------------------------------------ *
 * Failures, retries and the way out
 * ------------------------------------------------------------------ */

describe("RowAdjudicationDialog: failure and closing", () => {
  it("shows a thrown failure and leaves the write available to try again", async () => {
    // Only a missing row and a failed write throw, and neither decided
    // anything, so asking again is a different question from asking again
    // after an answer.
    vi.spyOn(financialAPI, "quarantineRow").mockRejectedValue(
      new Error("This row is not in this case.")
    )
    renderDialog()
    giveGrounds()
    fireEvent.click(submitButton())

    const failure = await screen.findByTestId("adjudication-error")
    expect(failure.textContent).toContain("This row is not in this case.")
    expect(screen.queryByTestId("adjudication-answer")).toBeNull()
    expect(submitButton()).toBeTruthy()
  })

  it("refuses a write with no case open, rather than addressing one to nothing", async () => {
    const write = vi.spyOn(financialAPI, "quarantineRow")
    renderDialog(makeRow(), { caseId: undefined })
    giveGrounds()
    fireEvent.click(submitButton())

    const failure = await screen.findByTestId("adjudication-error")
    expect(failure.textContent).toContain("No case is open")
    expect(write).not.toHaveBeenCalled()
  })

  it("takes the write away once an answer has arrived", async () => {
    // Any answer, including a refusal: asking the same question again gets the
    // same answer.
    vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(
      answer({ outcome: "unchanged", applied: false, reason: "Already set aside." })
    )
    renderDialog()
    giveGrounds()
    fireEvent.click(submitButton())

    await screen.findByTestId("adjudication-answer")
    expect(screen.queryByTestId("adjudication-submit")).toBeNull()
  })

  it("will not let the dialog be closed while the write is in flight", async () => {
    vi.spyOn(financialAPI, "quarantineRow").mockReturnValue(
      new Promise<RowAdjudication>(() => {})
    )
    renderDialog()
    giveGrounds()
    fireEvent.click(submitButton())

    // Awaited because the mutation reaches its pending state a microtask after
    // the click, so reading the button synchronously reads it before the write
    // has started and passes for the wrong reason.
    await waitFor(() => {
      const cancel = screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement
      expect(cancel.disabled).toBe(true)
    })
  })

  it("clears the answer and the grounds on the way out", async () => {
    // Cleared on closing rather than on opening, so a dialog reopened on a
    // different row cannot show the previous row's answer for the frame before
    // something replaces it.
    vi.spyOn(financialAPI, "quarantineRow").mockResolvedValue(answer())
    const { onClose } = renderDialog()
    giveGrounds()
    fireEvent.click(submitButton())
    await screen.findByTestId("adjudication-answer")

    fireEvent.click(screen.getByRole("button", { name: "Done" }))
    expect(onClose).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.queryByTestId("adjudication-answer")).toBeNull())
    expect(
      (screen.getByTestId("adjudication-reason-input") as HTMLTextAreaElement).value
    ).toBe("")
  })
})

/* ------------------------------------------------------------------ *
 * The row said back before anything is committed to
 * ------------------------------------------------------------------ */

describe("RowAdjudicationDialog: the row it names", () => {
  it("scales the amount by the row's own currency", () => {
    renderDialog(makeRow({ amount_minor: 123456, currency: "JPY" }))
    expect(screen.getByTestId("adjudication-amount").textContent).toContain("123,456")
  })

  it("marks an amount it could not scale rather than passing it off as a figure", () => {
    // Unmarked, this shows a count of minor units where a sum of money belongs,
    // and the person authorises a change against the wrong number.
    renderDialog(makeRow({ amount_minor: 1234.5 }))
    expect(screen.getByTestId("adjudication-amount-unscaled")).toBeTruthy()
  })

  it("says so when the ledger holds no description, rather than showing a blank", () => {
    renderDialog(makeRow({ description: null }))
    expect(screen.getByTestId("adjudication-no-description")).toBeTruthy()
  })
})
