/**
 * The dialog that reads a bank file to a person before storing it.
 *
 * The API is spied on rather than the hooks, and the query client is real, so
 * what these tests exercise is the sequence a person actually walks: type a
 * period, read, look, store. Mocking the hooks would leave the thing most
 * worth pinning untested, which is that the read genuinely happens before the
 * write and that the write is not offered when the reading says it would be
 * refused.
 *
 * Four claims here are load bearing rather than cosmetic:
 *
 *   - The read cannot be asked for without a period. Three of the four bank
 *     formats print two-digit years, so a file read without a stated range is
 *     a file filed under a guessed decade.
 *   - A reading that would not store offers no store button. A button that
 *     could only be refused is worse than no button.
 *   - `already_ingested` is not shown as a failure and does not claim rows
 *     were added, because it stored nothing and that was the right answer.
 *   - An absent balance is never rendered as zero. The file did not say the
 *     balance was nothing; it printed no balance at all.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { financialAPI, type FileIngestion, type FilePrecheck } from "../api"
import { SendToLedgerDialog } from "./SendToLedgerDialog"

const CASE_ID = "case-1"
const FILE_ID = "file-9"

function period(overrides: Partial<NonNullable<FilePrecheck["accounts"][number]["period"]>> = {}) {
  return {
    currency: "USD",
    start: "2024-01-01",
    end: "2024-03-31",
    start_source: "printed",
    end_source: "printed",
    opening: { source: "printed", amount_minor: 100000, currency: "USD" },
    closing: { source: "printed", amount_minor: 250000, currency: "USD" },
    ...overrides,
  }
}

function account(
  overrides: Partial<FilePrecheck["accounts"][number]> = {}
): FilePrecheck["accounts"][number] {
  return {
    account_key: "acct-a",
    identified: true,
    row_count: 42,
    institution_name: "First Union",
    identifier_as_printed: "****4021",
    account_type: "checking",
    holder_name: "R Mensah",
    currency: "USD",
    iban: null,
    bic: null,
    routing_number: null,
    period: period(),
    ...overrides,
  }
}

function precheck(overrides: Partial<FilePrecheck> = {}): FilePrecheck {
  return {
    file_id: FILE_ID,
    file_name: "statement.qbo",
    outcome: "readable",
    would_ingest: true,
    reason: null,
    detected_format: "OFX",
    parser_name: "ofx",
    parser_version: "1",
    extraction_layer: 0,
    source_shape: "native",
    reconciliation_status: "closed",
    proof_class: "p0",
    admissibility_reservations: [],
    row_count: 42,
    parsed_row_count: 42,
    skipped: [],
    earliest_ordering_date: "2024-01-03",
    latest_ordering_date: "2024-03-28",
    accounts: [account()],
    unattributed_keys: [],
    unattributed_row_count: 0,
    ...overrides,
  }
}

function ingestion(overrides: Partial<FileIngestion> = {}): FileIngestion {
  return {
    file_id: FILE_ID,
    file_name: "statement.qbo",
    outcome: "stored",
    stored: true,
    reason: null,
    run_id: "run-1",
    document_id: "doc-1",
    detected_format: "OFX",
    account_ids: ["acct-a"],
    period_ids: ["per-a"],
    transactions_stored: 42,
    unlinked_rows: 0,
    adjudication_id: null,
    ...overrides,
  }
}

function renderDialog(onClose = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SendToLedgerDialog
        caseId={CASE_ID}
        fileId={FILE_ID}
        fileName="statement.qbo"
        open
        onClose={onClose}
      />
    </QueryClientProvider>
  )
  return { ...view, onClose, queryClient }
}

/** Fill both date fields, which is the minimum the read will accept. */
function giveTheWindow(start = "2024-01-01", end = "2024-12-31") {
  fireEvent.change(screen.getByTestId("window-start"), { target: { value: start } })
  fireEvent.change(screen.getByTestId("window-end"), { target: { value: end } })
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe("SendToLedgerDialog", () => {
  it("will not read the file until a period has been given", () => {
    const read = vi.spyOn(financialAPI, "precheckFile")
    renderDialog()

    expect(screen.getByTestId("read-file")).toBeDisabled()

    // One date is not a window. A file with two-digit years read against half
    // a range is still a file read against a guess.
    fireEvent.change(screen.getByTestId("window-start"), {
      target: { value: "2024-01-01" },
    })
    expect(screen.getByTestId("read-file")).toBeDisabled()

    fireEvent.change(screen.getByTestId("window-end"), {
      target: { value: "2024-12-31" },
    })
    expect(screen.getByTestId("read-file")).toBeEnabled()
    expect(read).not.toHaveBeenCalled()
  })

  it("sends the period as typed, and the currency only when one was given", async () => {
    const read = vi.spyOn(financialAPI, "precheckFile").mockResolvedValue(precheck())
    renderDialog()

    giveTheWindow("1996-01-01", "2004-12-31")
    fireEvent.click(screen.getByTestId("read-file"))

    await waitFor(() => expect(read).toHaveBeenCalledTimes(1))
    expect(read).toHaveBeenCalledWith({
      caseId: CASE_ID,
      fileId: FILE_ID,
      windowStart: "1996-01-01",
      windowEnd: "2004-12-31",
      // Left off entirely rather than sent empty, so the endpoint's own
      // "assume nothing" path is the one that runs.
      defaultCurrency: undefined,
    })
  })

  it("passes a currency through when the reader supplied one", async () => {
    const read = vi.spyOn(financialAPI, "precheckFile").mockResolvedValue(precheck())
    renderDialog()

    giveTheWindow()
    fireEvent.change(screen.getByTestId("default-currency"), {
      target: { value: " gbp " },
    })
    fireEvent.click(screen.getByTestId("read-file"))

    await waitFor(() => expect(read).toHaveBeenCalledTimes(1))
    expect(read.mock.calls[0][0].defaultCurrency).toBe("gbp")
  })

  it("shows what the reading found, and stores nothing while it does", async () => {
    const read = vi.spyOn(financialAPI, "precheckFile").mockResolvedValue(precheck())
    const write = vi.spyOn(financialAPI, "ingestFile")
    renderDialog()

    giveTheWindow()
    fireEvent.click(screen.getByTestId("read-file"))

    expect(await screen.findByTestId("precheck-report")).toBeInTheDocument()
    expect(screen.getByText("Can be read")).toBeInTheDocument()
    expect(screen.getByTestId("precheck-rows")).toHaveTextContent("42 of 42 rows read")
    expect(screen.getByTestId("precheck-span")).toHaveTextContent(
      "Covering 2024-01-03 to 2024-03-28"
    )

    const acct = screen.getByTestId("precheck-account")
    expect(acct).toHaveTextContent("****4021 (R Mensah)")
    expect(acct).toHaveTextContent("42 rows")
    expect(acct).toHaveTextContent("Opening 1,000.00 USD / Closing 2,500.00 USD")

    expect(read).toHaveBeenCalledTimes(1)
    expect(write).not.toHaveBeenCalled()
    // The write is offered, not performed.
    expect(screen.getByTestId("store-file")).toBeInTheDocument()
  })

  it("offers no write when the reading says the endpoint would refuse one", async () => {
    vi.spyOn(financialAPI, "precheckFile").mockResolvedValue(
      precheck({
        outcome: "unattributable",
        would_ingest: false,
        unattributed_row_count: 3,
        unattributed_keys: ["8891"],
        accounts: [],
      })
    )
    renderDialog()

    giveTheWindow()
    fireEvent.click(screen.getByTestId("read-file"))

    expect(await screen.findByTestId("precheck-report")).toBeInTheDocument()
    expect(screen.getByText("Rows without an account")).toBeInTheDocument()
    expect(screen.getByTestId("precheck-unattributed")).toHaveTextContent(
      "3 rows name an account this file never introduces"
    )
    // A button that could only be refused is worse than no button.
    expect(screen.queryByTestId("store-file")).not.toBeInTheDocument()
    // The dates can still be changed, which is the only move left.
    expect(screen.getByTestId("read-again")).toBeInTheDocument()
  })

  it("takes the endpoint's flag rather than the outcome word when deciding to offer the write", async () => {
    // A word this build does not recognise, with `would_ingest: true`. If the
    // button were decided by the word, a backend one version ahead would
    // silently lose the ability to store.
    vi.spyOn(financialAPI, "precheckFile").mockResolvedValue(
      precheck({ outcome: "readable_with_notes", would_ingest: true })
    )
    renderDialog()

    giveTheWindow()
    fireEvent.click(screen.getByTestId("read-file"))

    expect(await screen.findByTestId("precheck-report")).toBeInTheDocument()
    expect(screen.getByText(/Unrecognised \(readable_with_notes\)/)).toBeInTheDocument()
    expect(screen.getByTestId("store-file")).toBeInTheDocument()
  })

  it("writes with the same period the reading used, and reports what went in", async () => {
    vi.spyOn(financialAPI, "precheckFile").mockResolvedValue(precheck())
    const write = vi.spyOn(financialAPI, "ingestFile").mockResolvedValue(
      ingestion({ transactions_stored: 42, unlinked_rows: 0 })
    )
    renderDialog()

    giveTheWindow("1996-01-01", "2004-12-31")
    fireEvent.click(screen.getByTestId("read-file"))
    fireEvent.click(await screen.findByTestId("store-file"))

    await waitFor(() => expect(write).toHaveBeenCalledTimes(1))
    expect(write).toHaveBeenCalledWith({
      caseId: CASE_ID,
      fileId: FILE_ID,
      windowStart: "1996-01-01",
      windowEnd: "2004-12-31",
      defaultCurrency: undefined,
    })

    const report = await screen.findByTestId("ingest-report")
    expect(report).toHaveTextContent("Added to the ledger")
    expect(report).toHaveTextContent("42 transactions added.")
    // The reading is replaced by the answer, so there is one account of what
    // happened on the screen rather than two.
    expect(screen.queryByTestId("precheck-report")).not.toBeInTheDocument()
  })

  it("does not report a file the case already holds as a failure", async () => {
    vi.spyOn(financialAPI, "precheckFile").mockResolvedValue(precheck())
    vi.spyOn(financialAPI, "ingestFile").mockResolvedValue(
      ingestion({
        outcome: "already_ingested",
        stored: false,
        transactions_stored: 0,
        run_id: null,
        reason: "This case already holds the rows from this file.",
      })
    )
    renderDialog()

    giveTheWindow()
    fireEvent.click(screen.getByTestId("read-file"))
    fireEvent.click(await screen.findByTestId("store-file"))

    const report = await screen.findByTestId("ingest-report")
    expect(report).toHaveTextContent("Already in the ledger")
    // Nothing went in, so nothing may claim to have. "0 transactions added"
    // over a good outcome reads as a failure.
    expect(report).not.toHaveTextContent("transactions added")
    expect(screen.queryByTestId("ingest-error")).not.toBeInTheDocument()
  })

  it("names the rows that could not be attached when some were", async () => {
    vi.spyOn(financialAPI, "precheckFile").mockResolvedValue(precheck())
    vi.spyOn(financialAPI, "ingestFile").mockResolvedValue(
      ingestion({ transactions_stored: 40, unlinked_rows: 2 })
    )
    renderDialog()

    giveTheWindow()
    fireEvent.click(screen.getByTestId("read-file"))
    fireEvent.click(await screen.findByTestId("store-file"))

    const report = await screen.findByTestId("ingest-report")
    expect(report).toHaveTextContent("40 transactions added.")
    expect(report).toHaveTextContent("2 rows could not be attached to an account")
  })

  it("shows a fault as a fault, and does not pass it off as a reading", async () => {
    vi.spyOn(financialAPI, "precheckFile").mockRejectedValue(
      new Error("Evidence file not found in this case")
    )
    renderDialog()

    giveTheWindow()
    fireEvent.click(screen.getByTestId("read-file"))

    expect(await screen.findByTestId("precheck-error")).toHaveTextContent(
      "Evidence file not found in this case"
    )
    expect(screen.queryByTestId("precheck-report")).not.toBeInTheDocument()
    // Still readable again, with a different window, without reopening.
    expect(screen.getByTestId("read-file")).toBeEnabled()
  })

  it("leaves an absent balance absent rather than printing it as zero", async () => {
    vi.spyOn(financialAPI, "precheckFile").mockResolvedValue(
      precheck({
        accounts: [
          account({
            period: period({
              opening: { source: "absent", amount_minor: null, currency: null },
            }),
          }),
        ],
      })
    )
    renderDialog()

    giveTheWindow()
    fireEvent.click(screen.getByTestId("read-file"))

    const acct = await screen.findByTestId("precheck-account")
    expect(acct).toHaveTextContent("Closing 2,500.00 USD")
    // The file printed no opening balance. Showing 0.00 would turn a fact it
    // did not state into one it did, and the arithmetic that checks a
    // statement against itself would then appear to have an opening to work
    // from.
    expect(acct).not.toHaveTextContent("Opening")
    expect(acct).not.toHaveTextContent("0.00 USD /")
  })

  it("scales a currency that has no minor unit without inventing decimals", async () => {
    vi.spyOn(financialAPI, "precheckFile").mockResolvedValue(
      precheck({
        accounts: [
          account({
            currency: "JPY",
            period: period({
              currency: "JPY",
              opening: { source: "printed", amount_minor: 250000, currency: "JPY" },
              closing: { source: "printed", amount_minor: 310000, currency: "JPY" },
            }),
          }),
        ],
      })
    )
    renderDialog()

    giveTheWindow()
    fireEvent.click(screen.getByTestId("read-file"))

    const acct = await screen.findByTestId("precheck-account")
    expect(acct).toHaveTextContent("Opening 250,000 JPY / Closing 310,000 JPY")
  })

  it("forgets the previous reading on the way out", async () => {
    vi.spyOn(financialAPI, "precheckFile").mockResolvedValue(precheck())
    const { onClose } = renderDialog()

    giveTheWindow()
    fireEvent.click(screen.getByTestId("read-file"))
    await screen.findByTestId("precheck-report")

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))

    expect(onClose).toHaveBeenCalledTimes(1)
    // Cleared on the way out, so a dialog reopened for a different file
    // cannot show this file's reading for the frame before the new one lands.
    await waitFor(() =>
      expect(screen.queryByTestId("precheck-report")).not.toBeInTheDocument()
    )
    expect(screen.getByTestId("window-start")).toHaveValue("")
  })
})
