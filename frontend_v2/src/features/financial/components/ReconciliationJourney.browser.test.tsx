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
import { StatementImportPanel } from "./StatementImportPanel"
import { BulkStatementDetails } from "./BulkStatementDetails"
import { BatchCurrencyEditor } from "./BatchCurrencyEditor"
import { AccountHistory } from "./AccountHistory"
import { ImportedStatementDetails } from "./ImportedStatementDetails"
import { StatementSourceTools } from "./StatementSourceTools"
import { useStatementWorkspace } from "../stores/statement-workspace"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { useInvestigationScopeStore } from "../stores/investigation-scope"

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
    <div className="h-96 border">
      Synthetic page image; original PDF is available through the source tools.
    </div>
  ),
}))
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
async function setup(quiet = false) {
  await service("/__fixture/reset", { method: "POST" })
  await service(`/__fixture/reconciled?quiet=${quiet}`, { method: "POST" })
  const ids = await service("/__fixture")
  sessionStorage.clear()
  useFinancialDraftStore.setState({ drafts: {} })
  useInvestigationScopeStore.getState().reset()
  useStatementWorkspace.setState({
    selections: {},
    pages: {},
    reviewChoices: {},
  })
  useStatementWorkspace
    .getState()
    .select(`anonymous:${ids.case_id}`, ids.file_id)
  vi.mocked(fetchAPI).mockImplementation((url, options) =>
    service(url, options)
  )
  await page.viewport(1360, 900)
  return ids as { case_id: string; file_id: string }
}
function mount(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <main className="p-4">{node}</main>
      </MemoryRouter>
    </QueryClientProvider>
  )
}
run(
  "sets month dates in a batch, saves a confirmed quiet period, and finds its balances in history",
  async () => {
    const { case_id: caseId, file_id: fileId } = await setup(true)
    mount(
      <BulkStatementDetails
        caseId={caseId}
        fileIds={[fileId]}
        datesOnly
        onSaved={() => {}}
      />
    )
    fireEvent.click(
      screen.getByRole("button", { name: "Set dates for selected statements" })
    )
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Select all 1 matching statements",
      })
    )
    fireEvent.change(screen.getByLabelText("Statement month and year"), {
      target: { value: "2024-02" },
    })
    fireEvent.change(screen.getByLabelText("How to apply account details"), {
      target: { value: "replace" },
    })
    expect(screen.getByLabelText("New statement end date")).toHaveValue(
      "2024-02-29"
    )
    fireEvent.click(
      screen.getByRole("button", { name: "Review changes for 1 statements" })
    )
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Save changes to 1 statements",
      })
    )
    await screen.findByRole("status")
    cleanup()
    const imported = vi.fn()
    mount(<StatementImportPanel caseId={caseId} onImported={imported} />)
    const check = await screen.findByRole("checkbox", {
      name: /I checked every page of this period/,
    })
    await waitFor(() => expect(check).toBeEnabled())
    expect(
      screen.getByRole("button", { name: "Save balances now" })
    ).toBeDisabled()
    fireEvent.click(check)
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Save balances now" })
      ).toBeEnabled()
    )
    fireEvent.click(screen.getByRole("button", { name: "Save balances now" }))
    await waitFor(() => expect(imported).toHaveBeenCalled())
    expect(imported.mock.calls[0][0].transaction_count).toBe(0)
    cleanup()
    mount(<AccountHistory caseId={caseId} />)
    await screen.findByRole("button", { name: "2024-02" })
    fireEvent.click(screen.getByRole("button", { name: "2024-02" }))
    await screen.findByText("No activity confirmed")
    expect(screen.getAllByText("12,450.00 EUR").length).toBe(2)
    expect(screen.getByRole("button", { name: "Open statement" })).toBeEnabled()
    expect((await service("/__fixture/payments")).payments).toHaveLength(0)
    await page.screenshot({
      path: "/private/tmp/loupe-quiet-account-history.png",
    })
    await page.viewport(420, 900)
    await waitFor(() =>
      expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(420)
    )
    cleanup()
  },
  60000
)

run(
  "holds a mismatched statement, preserves the draft, then imports exactly once after correction",
  async () => {
    const { case_id: caseId } = await setup()
    const imported = vi.fn()
    mount(<StatementImportPanel caseId={caseId} onImported={imported} />)
    const confirm = await screen.findByRole("button", {
      name: "Confirm import of 12 transactions",
    })
    await waitFor(() => expect(confirm).toBeEnabled())
    fireEvent.click(
      screen.getByRole("button", {
        name: "Show corrections and import choices",
      })
    )
    const amounts = screen.getAllByLabelText(/Credit /)
    const credit = amounts.find(
      (e) =>
        (e as HTMLInputElement).value === "125000.00" ||
        (e as HTMLInputElement).value === "125000"
    )!
    expect(credit).toBeDefined()
    fireEvent.change(credit, { target: { value: "125001" } })
    await waitFor(() => expect(confirm).toBeDisabled())
    expect((await service("/__fixture/payments")).payments).toHaveLength(0)
    fireEvent.change(credit, { target: { value: "125000" } })
    await waitFor(() => expect(confirm).toBeEnabled())
    fireEvent.click(confirm)
    await waitFor(() => expect(imported).toHaveBeenCalled())
    expect((await service("/__fixture/payments")).payments).toHaveLength(12)
    cleanup()
    mount(<AccountHistory caseId={caseId} />)
    fireEvent.click(await screen.findByRole("button", { name: "2023-12" }))
    fireEvent.click(screen.getByRole("button", { name: "View 12 payments" }))
    await screen.findByText("Saved statement payments")
    expect(screen.queryByRole("alert")).toBeNull()
    fireEvent.click(screen.getByRole("button", { name: "Close" }))
    expect(
      screen.getByRole("region", { name: "2023-12 activity details" })
    ).toBeVisible()
    cleanup()
  },
  60000
)

run(
  "copies extracted source text and opens a selectable original without losing an unfinished entry",
  async () => {
    const { file_id: fileId } = await setup()
    const originalFetch = globalThis.fetch
    vi.spyOn(globalThis, "fetch").mockImplementation((url, options) =>
      originalFetch(
        typeof url === "string" && url.startsWith("/api/evidence/")
          ? origin + url
          : url,
        options
      )
    )
    mount(
      <>
        <input
          aria-label="Unfinished payment description"
          defaultValue="Still adding this payment"
        />
        <StatementSourceTools
          fileId={fileId}
          page={1}
          text="Synthetic source reading for copying"
        />
      </>
    )
    fireEvent.click(screen.getByRole("button", { name: "Copy page text" }))
    const text = screen.getByLabelText(
      "Read page text · page 1"
    ) as HTMLTextAreaElement
    text.focus()
    expect(text.selectionEnd - text.selectionStart).toBe(text.value.length)
    fireEvent.click(
      screen.getByRole("button", { name: "Select text in original PDF" })
    )
    await waitFor(() =>
      expect(
        screen.getByTitle("Original statement, page 1").getAttribute("src")
      ).toMatch(/^blob:.*#page=1$/)
    )
    expect(screen.getByLabelText("Unfinished payment description")).toHaveValue(
      "Still adding this payment"
    )
    // Headless Chromium downloads PDFs; exercise its native viewer in the
    // separate visible run with VITE_FINANCIAL_NATIVE_PDF=1.
    if (import.meta.env.VITE_FINANCIAL_NATIVE_PDF === "1") {
      const nativeOpen = window.open.bind(window)
      const opened: { current: Window | null } = { current: null }
      vi.spyOn(window, "open").mockImplementation((...args) => {
        opened.current = nativeOpen(...args)
        return opened.current
      })
      fireEvent.click(
        screen.getByRole("button", { name: "Open original in new tab" })
      )
      await waitFor(() =>
        expect(opened.current?.location.href).toMatch(/^blob:.*#page=1$/)
      )
      expect(
        screen.getByLabelText("Unfinished payment description")
      ).toHaveValue("Still adding this payment")
      opened.current?.close()
    }
    fireEvent.click(screen.getByRole("button", { name: "Copy page text" }))
    await page.screenshot({ path: "/private/tmp/loupe-copyable-original.png" })
    cleanup()
    vi.restoreAllMocks()
  },
  60000
)

run(
  "confirms a lost currency response on retry and keeps the saved result after reopening",
  async () => {
    const { case_id: caseId } = await setup()
    const { batch_id: batchId } = await service("/__fixture/currency-batch", {
      method: "POST",
    })
    const attempts: unknown[] = []
    let lose = true
    vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
      const result = await service(url, options)
      if (options?.method === "POST" && url.includes("/currency?")) {
        attempts.push(options.body)
        if (lose) {
          lose = false
          throw Error("Synthetic response lost after the currency was saved")
        }
      }
      return result
    })
    mount(
      <BatchCurrencyEditor
        caseId={caseId}
        batchId={batchId}
        onSaved={() => {}}
      />
    )
    fireEvent.click(
      screen.getByRole("button", {
        name: "Set currency for selected statements",
      })
    )
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Select all 1 matching statements",
      })
    )
    fireEvent.change(
      screen.getByLabelText("Currency for selected statements"),
      { target: { value: "USD" } }
    )
    fireEvent.click(
      screen.getByRole("button", { name: /Apply USD to 1 statements/ })
    )
    await screen.findByRole("alert")
    expect(
      screen.getByRole("checkbox", { name: /Set currency for/ })
    ).toBeChecked()
    fireEvent.click(
      screen.getByRole("button", { name: /Apply USD to 1 statements/ })
    )
    await screen.findByText(
      /Earlier save confirmed: USD saved for 1 statements/
    )
    expect(attempts[1]).toEqual(attempts[0])
    cleanup()
    mount(
      <BatchCurrencyEditor
        caseId={caseId}
        batchId={batchId}
        onSaved={() => {}}
      />
    )
    fireEvent.click(
      screen.getByRole("button", {
        name: "Set currency for selected statements",
      })
    )
    await screen.findByText(/2023-12-31 · USD/)
    expect((await service("/__fixture/payments")).payments).toHaveLength(0)
    cleanup()
  },
  60000
)

run(
  "compares accounts with separate currencies and liabilities, preserves gaps and shared filters",
  async () => {
    const { case_id: caseId } = await setup(true)
    const { account_ids: ids } = await service("/__fixture/account-history", {
      method: "POST",
    })
    useInvestigationScopeStore
      .getState()
      .apply(caseId, { startDate: "2023-01-01", endDate: "2023-03-31" })
    mount(<AccountHistory caseId={caseId} />)
    await screen.findByRole("heading", { name: "EUR · Bank account balances" })
    expect(
      screen.getByRole("heading", { name: "USD · Bank account balances" })
    ).toBeVisible()
    expect(
      screen.getByRole("heading", { name: "USD · Credit card amounts owed" })
    ).toBeVisible()
    fireEvent.click(screen.getByRole("button", { name: "2023-02" }))
    expect(
      (await screen.findByRole("region", { name: "2023-02 activity details" }))
        .textContent
    ).toContain("Activity unknown")
    fireEvent.click(screen.getByRole("button", { name: "2023-01" }))
    expect(screen.getAllByText("No activity confirmed")).toHaveLength(4)
    useInvestigationScopeStore.getState().apply(caseId, {
      accountIds: [ids[0], ids[1]],
      startDate: "2023-01-01",
      endDate: "2023-03-31",
    })
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", {
          name: "USD · Credit card amounts owed",
        })
      ).toBeNull()
    )
    await screen.findByRole("heading", { name: "EUR · Bank account balances" })
    expect(screen.getAllByText("No activity confirmed")).toHaveLength(2)
    cleanup()
    mount(<AccountHistory caseId={caseId} />)
    await screen.findByRole("button", { name: "2023-03" })
    expect(
      screen.queryByRole("heading", { name: "USD · Bank account balances" })
    ).toBeNull()
    cleanup()
  },
  60000
)

run(
  "retains uncertain balance observations and confirms no activity on a later review",
  async () => {
    const { case_id: caseId } = await setup(true)
    const imported = vi.fn()
    mount(<StatementImportPanel caseId={caseId} onImported={imported} />)
    const save = await screen.findByRole("button", {
      name: "Save balances for review",
    })
    await waitFor(() => expect(save).toBeEnabled())
    fireEvent.click(save)
    await waitFor(() => expect(imported).toHaveBeenCalled())
    const sourceId = imported.mock.calls[0][0].source_document_id
    cleanup()
    mount(
      <ImportedStatementDetails
        caseId={caseId}
        sourceId={sourceId}
        initiallyOpen
      />
    )
    const check = await screen.findByRole("checkbox", {
      name: /I checked every page of this period/,
    })
    fireEvent.click(check)
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }))
    await screen.findByText(/Changes saved/)
    cleanup()
    mount(<AccountHistory caseId={caseId} />)
    fireEvent.click(await screen.findByRole("button", { name: "2023-12" }))
    await screen.findByText("No activity confirmed")
    expect((await service("/__fixture/payments")).payments).toHaveLength(0)
    cleanup()
  },
  60000
)
