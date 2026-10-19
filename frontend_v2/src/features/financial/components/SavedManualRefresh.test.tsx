import { beforeEach, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { financialAPI, type LedgerTransaction } from "../api"
import { useLedgerTransactions } from "../hooks/use-ledger-transactions"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { AddSavedStatementPayment } from "./AddSavedStatementPayment"
import { ImportedRecordsPanel } from "./ImportedRecordsPanel"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => <p>Synthetic original</p>,
}))
vi.mock("./PaymentCounterpartyPicker", () => ({
  PaymentCounterpartyPicker: () => null,
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))

const caseId = "synthetic-case"
const sourceId = "synthetic-source"
const description = "Synthetic added payment"

function LiveLedgerObserver() {
  const query = useLedgerTransactions(caseId, { sourceDocumentId: sourceId })
  return (
    <p>
      Current admitted payments: {query.data?.transactions.length ?? "loading"}
    </p>
  )
}

beforeEach(() => {
  useFinancialDraftStore.setState({ drafts: {} })
  vi.mocked(fetchAPI).mockReset()
})

it.each([false, true])(
  "refreshes active saved-record and ledger queries after save without reload (pending=%s)",
  async (pending) => {
    let saved: Record<string, unknown> | null = null
    const ledger = vi
      .spyOn(financialAPI, "getLedgerTransactions")
      .mockImplementation(async () => ({
        case_id: caseId,
        total: saved && !pending ? 1 : 0,
        transactions:
          saved && !pending
            ? [{ key: "saved-id", description } as LedgerTransaction]
            : [],
      }))
    vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
      if (url.includes("/details?"))
        return {
          case_id: caseId,
          source_document_id: sourceId,
          evidence_file_id: "synthetic-file",
          revision: "a".repeat(64),
          currency: "EUR",
          pages: [1],
          details: {
            holder: "Synthetic holder",
            institution: "Synthetic bank",
            account_number: "0001",
          },
        } as never
      if (url.includes("/manual-payment?")) {
        saved = (options?.body as { row: Record<string, unknown> }).row
        return {
          transaction_id: pending ? null : "saved-id",
          pending_reconciliation: pending,
        } as never
      }
      if (url.includes("/incomplete-records?"))
        return {
          total: saved && pending ? 1 : 0,
          records:
            saved && pending
              ? [
                  {
                    id: saved.id,
                    source_document_id: sourceId,
                    evidence_file_id: "synthetic-file",
                    filename: "Synthetic statement.pdf",
                    currency: "EUR",
                    page_number: 1,
                    locator: { kind: "page_only", page: 1 },
                    original_text: "Investigator entry",
                    missing_fields: [],
                    version: 0,
                    fields: { ...saved, excluded: false },
                  },
                ]
              : [],
        } as never
      throw Error(`Unexpected synthetic endpoint ${url}`)
    })
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    })
    const onSaved = vi.fn()
    const view = render(
      <QueryClientProvider client={client}>
        <LiveLedgerObserver />
        <ImportedRecordsPanel
          caseId={caseId}
          params={{ sourceDocumentId: sourceId }}
          onOpen={vi.fn()}
        />
        <AddSavedStatementPayment
          caseId={caseId}
          sourceId={sourceId}
          onSaved={onSaved}
        />
      </QueryClientProvider>
    )
    try {
      await screen.findByText("Current admitted payments: 0")
      await waitFor(() =>
        expect(
          screen.queryByText("Checking imported records…")
        ).not.toBeInTheDocument()
      )
      fireEvent.click(
        screen.getByRole("button", { name: "Add a missed transaction" })
      )
      await screen.findByText("Synthetic original")
      fireEvent.change(screen.getByLabelText("Missed payment date"), {
        target: { value: "2026-01-02" },
      })
      fireEvent.change(screen.getByLabelText("Description"), {
        target: { value: description },
      })
      fireEvent.change(screen.getByLabelText("Money in or out"), {
        target: { value: "credit" },
      })
      fireEvent.change(screen.getByLabelText("Amount (EUR)"), {
        target: { value: "12.34" },
      })
      fireEvent.click(screen.getByRole("button", { name: "Save payment" }))
      if (pending) {
        await screen.findByText(/Payment saved for review\./)
        expect(
          await screen.findByText(/1 imported record has missing values/)
        ).toBeInTheDocument()
        expect(
          screen.getByText("Current admitted payments: 0")
        ).toBeInTheDocument()
        expect(onSaved).not.toHaveBeenCalled()
      } else {
        await screen.findByText("Current admitted payments: 1")
        expect(onSaved).toHaveBeenCalledWith("saved-id")
        expect(
          screen.queryByText(/1 imported record has missing values/)
        ).not.toBeInTheDocument()
      }
      expect(ledger).toHaveBeenCalledTimes(2)
      expect(
        vi
          .mocked(fetchAPI)
          .mock.calls.filter(([url]) => url.includes("/incomplete-records?"))
          .length
      ).toBe(2)
      expect(
        vi
          .mocked(fetchAPI)
          .mock.calls.filter(([url]) => url.includes("/manual-payment?")).length
      ).toBe(1)
    } finally {
      view.unmount()
      client.clear()
      ledger.mockRestore()
    }
  }
)
