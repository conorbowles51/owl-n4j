import "@/styles/globals.css"
import "../financial-workspace.css"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import {
  StatementImportPanel,
  type StatementImportReceipt,
} from "./StatementImportPanel"
import { ImportedStatementDetails } from "./ImportedStatementDetails"
import { BulkStatementDetails } from "./BulkStatementDetails"
import { InvestigationTransactionTable } from "./InvestigationTransactionTable"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { useStatementWorkspace } from "../stores/statement-workspace"
import type { LedgerTransaction } from "../api"

// Transport points at real FastAPI routes and a disposable SQL database. Only
// authentication and the PDF canvas are substituted; no business API is mocked.
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({
    canEdit: true,
    canUpload: true,
    ready: true,
    error: false,
  }),
}))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => (
    <div className="h-96 border p-4">
      Synthetic source canvas; parser/locator acceptance is tested separately.
    </div>
  ),
}))
vi.mock("./PdfReviewIntake", () => ({ PdfReviewIntake: () => null }))
const origin = "http://127.0.0.1:58129"
async function service(
  path: string,
  options: { method?: string; body?: unknown; signal?: AbortSignal | null } = {}
) {
  const response = await fetch(origin + path, {
    ...options,
    headers: { "Content-Type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  })
  const result = await response.json()
  if (!response.ok)
    throw Error(
      typeof result.detail === "string" ? result.detail : JSON.stringify(result)
    )
  return result
}
const run = import.meta.env.VITE_FINANCIAL_REAL_SERVICE === "1" ? it : it.skip
run(
  "saves a review, imports, reopens current values and corrects the same bulk selection twice through real persistence",
  async () => {
    await service("/__fixture/reset", { method: "POST" })
    const fixture = (await service("/__fixture")) as {
      synthetic: boolean
      case_id: string
      file_id: string
    }
    expect(fixture.synthetic).toBe(true)
    const { case_id: caseId, file_id: fileId } = fixture
    vi.mocked(fetchAPI).mockImplementation((url, options) =>
      service(url, options)
    )
    useFinancialDraftStore.setState({ drafts: {} })
    useStatementWorkspace.setState({
      selections: {},
      pages: {},
      reviewChoices: {},
    })
    await page.viewport(1360, 900)
    const mount = (content: React.ReactNode) =>
      render(
        <QueryClientProvider
          client={
            new QueryClient({
              defaultOptions: {
                queries: { retry: false },
                mutations: { retry: false },
              },
            })
          }
        >
          <MemoryRouter>{content}</MemoryRouter>
        </QueryClientProvider>
      )
    let receipt: StatementImportReceipt | undefined
    mount(
      <StatementImportPanel
        caseId={caseId}
        onImported={(value) => {
          receipt = value
        }}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: "Import a statement" }))
    await waitFor(() =>
      expect(
        screen.getByLabelText("Uploaded statement").querySelectorAll("option")
          .length
      ).toBeGreaterThan(1)
    )
    fireEvent.change(screen.getByLabelText("Uploaded statement"), {
      target: { value: fileId },
    })
    fireEvent.change(await screen.findByLabelText("Account holder"), {
      target: { value: "Synthetic reviewed company" },
    })
    fireEvent.click(
      screen.getByRole("button", { name: "Save account details" })
    )
    await screen.findByText(
      "Account details saved to the case.",
      {},
      { timeout: 5000 }
    )
    fireEvent.click(
      await screen.findByRole("button", {
        name: /Import 12 payments and view Transactions/,
      })
    )
    await waitFor(() => expect(receipt?.source_document_id).toBeTruthy(), {
      timeout: 15000,
    })
    const sourceId = receipt!.source_document_id!
    let saved = (await service("/__fixture/payments")) as {
      payments: LedgerTransaction[]
    }
    expect(saved.payments).toHaveLength(12)
    expect(
      saved.payments.every(
        (row) => row.account_holder === "Synthetic reviewed company"
      )
    ).toBe(true)
    cleanup()
    mount(
      <InvestigationTransactionTable
        rows={saved.payments}
        selected={[]}
        onToggle={() => {}}
        showAccount
      />
    )
    expect(screen.getAllByRole("row").length).toBe(13)
    cleanup()
    mount(
      <ImportedStatementDetails
        caseId={caseId}
        sourceId={sourceId}
        withSource
        initiallyOpen
      />
    )
    fireEvent.change(await screen.findByLabelText("Saved closing balance"), {
      target: { value: "77.25" },
    })
    fireEvent.change(screen.getByLabelText("Saved period start"), {
      target: { value: "2026-01-01" },
    })
    fireEvent.change(screen.getByLabelText("Saved period end"), {
      target: { value: "2026-01-31" },
    })
    fireEvent.change(screen.getByLabelText("closing balance page"), {
      target: { value: "1" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))
    await screen.findByText(/Changes saved/)
    cleanup()
    mount(
      <ImportedStatementDetails
        caseId={caseId}
        sourceId={sourceId}
        withSource
        initiallyOpen
      />
    )
    expect(await screen.findByLabelText("Saved closing balance")).toHaveValue(
      "77.25"
    )
    expect(screen.getByLabelText("Saved period end")).toHaveValue("2026-01-31")
    cleanup()
    for (const holder of [
      "Synthetic wrong holder",
      "Synthetic corrected holder",
    ]) {
      mount(
        <BulkStatementDetails
          caseId={caseId}
          fileIds={[fileId]}
          onSaved={() => {}}
        />
      )
      fireEvent.click(
        screen.getByRole("button", { name: "Edit account details" })
      )
      fireEvent.click(
        await screen.findByRole("button", {
          name: "Select all 1 matching statements",
        })
      )
      fireEvent.change(screen.getByLabelText("How to apply account details"), {
        target: { value: "replace" },
      })
      fireEvent.click(screen.getByLabelText("Change account holder"))
      fireEvent.change(screen.getByLabelText("New account holder"), {
        target: { value: holder },
      })
      fireEvent.click(
        screen.getByRole("button", { name: "Review changes for 1 statements" })
      )
      fireEvent.click(
        await screen.findByRole("button", {
          name: "Save changes to 1 statements",
        })
      )
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
      saved = await service("/__fixture/payments")
      expect(saved.payments).toHaveLength(12)
      expect([
        ...new Set(saved.payments.map((row) => row.account_holder)),
      ]).toEqual([holder])
      cleanup()
    }
    const reopened = await service(
      `/api/financial/statement-import/${fileId}?case_id=${caseId}`
    )
    expect(reopened.current_import.details.holder).toBe(
      "Synthetic corrected holder"
    )
    expect(reopened.current_import.transaction_count).toBe(12)
  },
  60000
)
