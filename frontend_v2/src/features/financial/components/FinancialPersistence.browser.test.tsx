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
  within,
} from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import {
  StatementImportPanel,
  type StatementImportReceipt,
} from "./StatementImportPanel"
import { ImportedStatementDetails } from "./ImportedStatementDetails"
import { BulkStatementDetails } from "./BulkStatementDetails"
import { StatementFilesPanel } from "./StatementFilesPanel"
import { FinancialBatchPanel } from "./FinancialBatchPanel"
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
  "chooses bank and credit-card sections from one PDF, imports and reopens each independently",
  async () => {
    await service("/__fixture/reset", { method: "POST" })
    await service("/__fixture/mixed-statements", { method: "POST" })
    const { case_id: caseId, file_id: fileId } = await service("/__fixture")
    useFinancialDraftStore.setState({ drafts: {} })
    useStatementWorkspace.setState({
      selections: {},
      pages: {},
      reviewChoices: {},
    })
    vi.mocked(fetchAPI)
      .mockClear()
      .mockImplementation((url, options) => service(url, options))
    await page.viewport(1360, 900)
    let receipt: StatementImportReceipt | undefined
    const mount = () =>
      render(
        <QueryClientProvider
          client={
            new QueryClient({ defaultOptions: { queries: { retry: false } } })
          }
        >
          <MemoryRouter>
            <StatementImportPanel
              caseId={caseId}
              onImported={(value) => {
                receipt = value
              }}
            />
          </MemoryRouter>
        </QueryClientProvider>
      )
    mount()
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
    const card = await screen.findByRole("button", {
      name: /Credit One Bank.*Credit card/,
    })
    expect(
      screen.getByRole("button", { name: /Andrews.*Checking account/ })
    ).toBeVisible()
    expect(
      screen.getByRole("button", { name: /Andrews.*Savings account/ })
    ).toBeVisible()
    fireEvent.click(card)
    await screen.findByText(
      /Debits increase the amount owed; credits reduce it/
    )
    expect(screen.getByLabelText("Statement account")).toHaveTextContent(
      "Credit card"
    )
    fireEvent.click(
      await screen.findByRole("button", {
        name: /Import 3 payments and view Transactions/,
      })
    )
    await waitFor(() => expect(receipt?.transaction_count).toBe(3), {
      timeout: 15000,
    })
    const cardAccount = receipt!.account_id
    cleanup()
    mount()
    fireEvent.click(screen.getByRole("button", { name: "Import a statement" }))
    await screen.findByText(/Already imported: 3 payments/)
    fireEvent.click(
      screen.getByRole("button", { name: "Choose another statement period" })
    )
    fireEvent.click(
      await screen.findByRole("button", { name: /Andrews.*Checking account/ })
    )
    fireEvent.click(
      await screen.findByRole("button", {
        name: /Import 1 payment.*view Transactions/,
      })
    )
    await waitFor(() => expect(receipt?.transaction_count).toBe(1), {
      timeout: 15000,
    })
    expect(receipt!.account_id).not.toBe(cardAccount)
    const saved = await service("/__fixture/payments")
    expect(saved.payments).toHaveLength(4)
    cleanup()
    mount()
    fireEvent.click(screen.getByRole("button", { name: "Import a statement" }))
    await screen.findByText(/Already imported: 1 payments/)
    fireEvent.click(
      screen.getByRole("button", { name: "Choose another statement period" })
    )
    fireEvent.click(
      await screen.findByRole("button", {
        name: /Credit One Bank.*Credit card/,
      })
    )
    await screen.findByText(/Already imported: 3 payments/)
    await page.screenshot({
      path: "/private/tmp/loupe-mixed-statements-review/mixed-reopened.png",
    })
    cleanup()
  },
  60000
)
run(
  "explains batch checks, retains a reason through review, and clears it after a saved bulk correction",
  async () => {
    await service("/__fixture/reset", { method: "POST" })
    const { case_id: caseId } = await service("/__fixture")
    const { batch_id: batchId } = await service(
      "/__fixture/review-reasons-batch",
      { method: "POST" }
    )
    useFinancialDraftStore.setState({ drafts: {} })
    useStatementWorkspace.setState({ selections: {}, reviewChoices: {} })
    vi.mocked(fetchAPI)
      .mockClear()
      .mockImplementation((url, options) => service(url, options))
    await page.viewport(1360, 900)
    const mount = (filter = "") =>
      render(
        <QueryClientProvider
          client={
            new QueryClient({ defaultOptions: { queries: { retry: false } } })
          }
        >
          <MemoryRouter
            initialEntries={[
              `/cases/${caseId}/financial?view=statements&batch=${batchId}${filter}`,
            ]}
          >
            <main className="p-5">
              <FinancialBatchPanel caseId={caseId} />
            </main>
          </MemoryRouter>
        </QueryClientProvider>
      )
    mount()
    await screen.findByText("No prepared statements are blocked from import.")
    await screen.findByText("1 can be imported with checks retained.")
    await page.screenshot({
      path: "/private/tmp/loupe-review-checks-before.png",
    })
    const reasonButton = page.getByRole("button", {
      name: "Show statements: Missing account holder",
      exact: true,
    })
    await reasonButton.click()
    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          name: "Statements: Missing account holder",
        })
      ).toHaveFocus()
    )
    await screen.findByText(
      /Import covers all available statements in this batch/
    )
    await page
      .getByRole("button", { name: "Review problems", exact: true })
      .click()
    await screen.findByText(
      /Previous and next stay within the selected review reason/
    )
    await page
      .getByRole("button", { name: "Back to bulk import", exact: true })
      .click()
    await screen.findByRole("heading", {
      name: "Statements: Missing account holder",
    })
    await page
      .getByRole("button", { name: "Edit account details", exact: true })
      .click()
    await page
      .getByRole("button", {
        name: "Select all 1 matching statements",
        exact: true,
      })
      .click()
    await page.getByLabelText("Change account holder", { exact: true }).click()
    await page
      .getByLabelText("New account holder", { exact: true })
      .fill("Synthetic reviewed holder")
    await page
      .getByRole("button", {
        name: "Review changes for 1 statements",
        exact: true,
      })
      .click()
    await page
      .getByRole("button", {
        name: "Save changes to 1 statements",
        exact: true,
      })
      .click()
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    await screen.findByText(/No statements match this reason now/)
    expect(
      screen.getByRole("heading", {
        name: "Statements: Missing account holder",
      })
    ).toBeVisible()
    const status = await service(
      `/api/financial/statement-import/batches/${batchId}?case_id=${caseId}`
    )
    expect(
      status.review_summary.groups.some(
        (group: { id: string }) => group.id === "holder"
      )
    ).toBe(false)
    expect(status.items[0].holder).toBe("Synthetic reviewed holder")
    expect(status.available_transactions).toBe(12)
    expect((await service("/__fixture/payments")).payments).toHaveLength(0)
    cleanup()
    mount("&batchCheck=holder")
    await screen.findByText(/No statements match this reason now/)
    await page
      .getByRole("button", { name: "Clear reason filter", exact: true })
      .click()
    await screen.findByText(/Synthetic reviewed holder/)
    await screen.findByRole("button", {
      name: "Import 12 transactions",
    })
    screen
      .getByRole("heading", {
        name: "Prepare statements for import",
      })
      .scrollIntoView()
    await page.screenshot({ path: "/private/tmp/loupe-review-checks-wide.png" })
    await page.viewport(760, 1000)
    await page.screenshot({
      path: "/private/tmp/loupe-review-checks-narrow.png",
    })
    cleanup()
  },
  45000
)
run(
  "retries a missing prepared reading from the batch and imports once through real persistence",
  async () => {
    await service("/__fixture/reset", { method: "POST" })
    const { case_id: caseId, file_id: fileId } = await service("/__fixture")
    const { batch_id: batchId } = await service(
      "/__fixture/missing-reading-batch",
      { method: "POST" }
    )
    vi.mocked(fetchAPI)
      .mockClear()
      .mockImplementation((url, options) => service(url, options))
    await page.viewport(1360, 900)
    const mount = () =>
      render(
        <QueryClientProvider
          client={
            new QueryClient({ defaultOptions: { queries: { retry: false } } })
          }
        >
          <MemoryRouter
            initialEntries={[
              `/cases/${caseId}/financial?view=statements&batch=${batchId}`,
            ]}
          >
            <main className="p-5">
              <FinancialBatchPanel caseId={caseId} />
            </main>
          </MemoryRouter>
        </QueryClientProvider>
      )
    mount()
    await screen.findByText(/The prepared reading is unavailable/)
    await page
      .getByRole("button", { name: "Retry this file", exact: true })
      .click()
    await screen.findByText(/Retry accepted for/)
    await screen.findByText(/Waiting to process/)
    const prefix = `/api/financial/statement-import/batches/${batchId}`
    expect(
      await service(`${prefix}/files/${fileId}/retry?case_id=${caseId}`, {
        method: "POST",
      })
    ).toEqual({ queued: false, status: "waiting" })
    await service(`/__fixture/advance-batch/${batchId}`, { method: "POST" })
    fireEvent.click(screen.getByRole("button", { name: "Refresh batch" }))
    await waitFor(() =>
      expect(
        screen.queryByText(/The prepared reading is unavailable/)
      ).toBeNull()
    )
    expect((await service("/__fixture/payments")).payments).toHaveLength(0)
    await page
      .getByRole("button", { name: "Import 12 transactions", exact: true })
      .click()
    await screen.findByText(/Importing 1 statements/)
    await service(`/__fixture/advance-batch/${batchId}`, { method: "POST" })
    fireEvent.click(screen.getByRole("button", { name: "Refresh batch" }))
    await screen.findByRole("button", { name: "No new statements to import" })
    const saved = (await service("/__fixture/payments")).payments
    expect(saved).toHaveLength(12)
    cleanup()
    mount()
    await screen.findByRole("button", { name: "No new statements to import" })
    expect(screen.queryByRole("button", { name: "Retry this file" })).toBeNull()
    expect(
      (await service("/__fixture/payments")).payments.map(
        (p: { id: string }) => p.id
      )
    ).toEqual(saved.map((p: { id: string }) => p.id))
    await page.screenshot({
      path: "/private/tmp/loupe-caal-review/retry-result.png",
    })
    cleanup()
  },
  30000
)
run(
  "keeps ordinary Evidence PDFs out of Financial until explicitly sent, including after reopening",
  async () => {
    await service("/__fixture/reset", { method: "POST" })
    const { case_id: caseId } = (await service("/__fixture")) as {
      case_id: string
    }
    vi.mocked(fetchAPI).mockImplementation((url, options) =>
      service(url, options)
    )
    await page.viewport(1360, 900)
    const mount = () =>
      render(
        <QueryClientProvider
          client={
            new QueryClient({ defaultOptions: { queries: { retry: false } } })
          }
        >
          <MemoryRouter>
            <StatementFilesPanel caseId={caseId} register />
          </MemoryRouter>
        </QueryClientProvider>
      )
    type Files = {
      files: {
        id: string
        original_filename: string
        status: string
        engine_job_id?: string | null
      }[]
    }
    const before = (await service(`/api/evidence?case_id=${caseId}`)) as Files
    expect(
      before.files.some(
        (file) => file.original_filename === "Interview transcript.pdf"
      )
    ).toBe(true)
    const pending = before.files.find(
      (file) => file.original_filename === "Unsent statement.pdf"
    )!
    expect(pending.status).toBe("unprocessed")
    mount()
    await screen.findByLabelText("Select statement-1.pdf")
    expect(screen.queryByText("Interview transcript.pdf")).toBeNull()
    expect(screen.queryByText("Unsent statement.pdf")).toBeNull()
    fireEvent.click(
      screen.getByRole("button", { name: "Choose from Evidence" })
    )
    fireEvent.click(
      await screen.findByLabelText("Select file Unsent statement.pdf")
    )
    fireEvent.click(
      screen.getByRole("button", { name: "Review selected files" })
    )
    await screen.findByText("1 files to send to Financial")
    fireEvent.click(screen.getByRole("button", { name: /Send .*Financial/ }))
    await screen.findByLabelText("Select Unsent statement.pdf")
    expect(screen.queryByText("Interview transcript.pdf")).toBeNull()
    cleanup()
    mount()
    await screen.findByLabelText("Select Unsent statement.pdf")
    expect(screen.queryByText("Interview transcript.pdf")).toBeNull()
    const after = (await service(`/api/evidence?case_id=${caseId}`)) as Files
    expect(after.files.map((file) => file.id).sort()).toEqual(
      before.files.map((file) => file.id).sort()
    )
    expect(after.files.find((file) => file.id === pending.id)?.status).toBe(
      "unprocessed"
    )
    expect(after.files.every((file) => !file.engine_job_id)).toBe(true)
    cleanup()
  },
  30000
)
run(
  "includes CSV, Office and image sources without PDF jobs, then removes, restores and reopens",
  async () => {
    await service("/__fixture/reset", { method: "POST" })
    const { case_id: caseId } = await service("/__fixture")
    vi.mocked(fetchAPI)
      .mockClear()
      .mockImplementation((url, options) => service(url, options))
    await page.viewport(1360, 900)
    const mount = () =>
      render(
        <QueryClientProvider
          client={
            new QueryClient({ defaultOptions: { queries: { retry: false } } })
          }
        >
          <MemoryRouter>
            <StatementFilesPanel caseId={caseId} register />
          </MemoryRouter>
        </QueryClientProvider>
      )
    const names = [
      "Payments.csv",
      "Accounts.xlsx",
      "Invoice.docx",
      "Receipt.png",
      "Legacy.xls",
    ]
    const before = await service(`/api/evidence?case_id=${caseId}`)
    mount()
    await screen.findByLabelText("Select statement-1.pdf")
    expect(screen.queryByText("Payments.csv")).toBeNull()
    fireEvent.click(
      screen.getByRole("button", { name: "Choose from Evidence" })
    )
    for (const name of names)
      fireEvent.click(await screen.findByLabelText(`Select file ${name}`))
    fireEvent.click(
      screen.getByRole("button", { name: "Review selected files" })
    )
    await screen.findByRole("heading", { name: "5 files to send to Financial" })
    fireEvent.click(
      screen.getByRole("button", { name: "Send 5 files to Financial" })
    )
    await screen.findByRole("article", {
      name: "Financial source Payments.csv",
    })
    for (const name of names)
      expect(
        screen.getByRole("article", { name: `Financial source ${name}` })
      ).toBeVisible()
    expect(screen.queryByText("Interview transcript.pdf")).toBeNull()
    expect(screen.queryByLabelText("Select Payments.csv")).toBeNull()
    expect(
      screen.getByRole("button", { name: "Select all 2 shown files" })
    ).toBeEnabled()
    const source = before.files.find(
      (file: { original_filename: string }) =>
        file.original_filename === "Payments.csv"
    )
    expect(
      screen
        .getAllByRole("link", { name: "Open source in Evidence" })
        .some(
          (link) =>
            link.getAttribute("href") ===
            `/cases/${caseId}/evidence?file=${source.id}&from=financial`
        )
    ).toBe(true)
    fireEvent.click(
      screen.getByRole("button", {
        name: "Remove from Financial: Payments.csv",
      })
    )
    fireEvent.click(
      screen.getByRole("button", { name: "Remove from Financial" })
    )
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
    await waitFor(() =>
      expect(
        screen.queryByRole("article", { name: "Financial source Payments.csv" })
      ).toBeNull()
    )
    fireEvent.click(
      await screen.findByRole("button", { name: /^Removed files/ })
    )
    await screen.findByRole("article", {
      name: "Financial source Payments.csv",
    })
    fireEvent.click(
      screen.getByRole("button", { name: "Restore to Financial: Payments.csv" })
    )
    await waitFor(() =>
      expect(
        screen.queryByRole("article", { name: "Financial source Payments.csv" })
      ).toBeNull()
    )
    cleanup()
    mount()
    await screen.findByRole("article", {
      name: "Financial source Payments.csv",
    })
    const after = await service(`/api/evidence?case_id=${caseId}`)
    expect(after.files.map((file: { id: string }) => file.id).sort()).toEqual(
      before.files.map((file: { id: string }) => file.id).sort()
    )
    expect(
      after.files.every(
        (file: { engine_job_id?: string }) => !file.engine_job_id
      )
    ).toBe(true)
    expect(
      vi.mocked(fetchAPI).mock.calls.some(([url]) => url.includes("/batches?"))
    ).toBe(false)
    fireEvent.change(screen.getByLabelText("Search statement files"), {
      target: { value: "Payments.csv" },
    })
    await page
      .getByRole("article", { name: "Financial source Payments.csv" })
      .screenshot({ path: "/private/tmp/loupe-financial-source-formats.png" })
    await page.viewport(420, 900)
    await page
      .getByRole("article", { name: "Financial source Payments.csv" })
      .screenshot({
        path: "/private/tmp/loupe-financial-source-formats-narrow.png",
      })
    cleanup()
  },
  30000
)
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

run(
  "shows background recovery and opens the recovered statement through real persistence",
  async () => {
    await service("/__fixture/reset", { method: "POST" })
    const fixture = (await service("/__fixture")) as {
      case_id: string
      file_id: string
    }
    await service("/__fixture/recovery", { method: "POST" })
    vi.mocked(fetchAPI).mockImplementation((url, options) =>
      service(url, options)
    )
    await page.viewport(1360, 900)
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const open = vi.fn()
    const mount = () =>
      render(
        <QueryClientProvider client={client}>
          <MemoryRouter>
            <StatementFilesPanel
              caseId={fixture.case_id}
              register
              onOpen={open}
            />
          </MemoryRouter>
        </QueryClientProvider>
      )
    const first = mount()
    await screen.findByRole("region", {
      name: "Recovery of previous statements",
    })
    fireEvent.click(screen.getByRole("button", { name: "Pause recovery" }))
    await screen.findByRole("button", { name: "Resume recovery" })
    await service("/__fixture/recover-next", { method: "POST" })
    const paused = (await service("/__fixture/payments")) as {
      payments: unknown[]
    }
    expect(paused.payments).toHaveLength(11)
    fireEvent.click(screen.getByRole("button", { name: "Resume recovery" }))
    await screen.findByRole("button", { name: "Pause recovery" })
    await service("/__fixture/recover-next", { method: "POST" })
    await client.invalidateQueries({
      queryKey: ["financial-deployment-recovery", fixture.case_id],
    })
    fireEvent.click(screen.getByText("Review recovery results"))
    await screen.findByText(/1 missing payment/)
    await page
      .getByRole("region", { name: "Recovery of previous statements" })
      .screenshot({ path: "/private/tmp/loupe-recovery-results.png" })
    first.unmount()
    mount()
    fireEvent.click(await screen.findByText("Review recovery results"))
    const resultRow = screen.getByText(/1 missing payment/).closest("li")!
    fireEvent.click(
      within(resultRow).getByRole("button", { name: "Open statement" })
    )
    expect(
      Object.values(useStatementWorkspace.getState().selections).some(
        (value) => value.fileId === fixture.file_id
      )
    ).toBe(true)
    expect(open).toHaveBeenCalled()
    await service("/__fixture/recover-next", { method: "POST" })
    const recovered = (await service("/__fixture/payments")) as {
      payments: unknown[]
    }
    expect(recovered.payments).toHaveLength(12)
    cleanup()
  },
  30000
)
