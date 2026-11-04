/**
 * Trends shows its figures from one server answer and reads every payment only when the download asks for them
 * (d5b330d1: every payment is 64 MB; the page took 45-67 s before anything showed while it waited for them).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import fixture from "../lib/trends-parity.fixture.json"
import { InvestigatorTrends } from "./InvestigatorTrends"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { useInvestigationScopeStore } from "../stores/investigation-scope"

const calls = vi.hoisted(() => [] as string[])
const server = vi.hoisted(() => ({ unavailable: false }))
const CASE = fixture.case_id
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(async (url: string) => {
    calls.push(url)
    if (url.startsWith("/api/financial/ledger-trends-view?"))
      return server.unavailable
        ? { case_id: CASE, available: false, reason: "a date in year 0000" }
        : { case_id: CASE, available: true, ...fixture.scenarios[0].server }
    if (url.startsWith("/api/financial/ledger?"))
      return { case_id: CASE, total: fixture.rows.length, transactions: fixture.rows }
    throw Error(`unexpected request ${url}`)
  }),
}))
vi.mock("../hooks/use-statement-register", () => ({
  useStatementRegister: () => ({
    imports: { data: undefined, isError: false, refetch: vi.fn() },
    files: { data: undefined },
  }),
}))
vi.mock("./AccountHistory", () => ({ AccountHistory: () => null }))
vi.mock("./InvestigationWorkspaceParts", async (original) => ({
  ...(await original<typeof import("./InvestigationWorkspaceParts")>()),
  WorkspaceScope: () => null,
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: false }),
}))

afterEach(() => {
  cleanup()
  calls.length = 0
  server.unavailable = false
  useInvestigationScopeStore.getState().reset()
  useFinancialDraftStore.setState({ drafts: {} })
})

const renderPage = (client = new QueryClient()) =>
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <InvestigatorTrends caseId={CASE} />
      </MemoryRouter>
    </QueryClientProvider>
  )

it("shows the comparison from one request, without reading every payment", async () => {
  renderPage()
  const changed = await screen.findByRole("region", { name: "What changed" })
  const out = within(changed).getByRole("heading", { name: "Money out" }).closest("article")!
  // The server's figures for the default periods (January against February 2021).
  const debit = fixture.scenarios[0].server.result!.totals.find((t) => t.direction === "debit")!
  expect(out).toHaveTextContent(`Earlier · ${debit.beforeCount} payments`)
  expect(out).toHaveTextContent(`Later · ${debit.afterCount} payments`)
  expect(screen.getByRole("table", { name: "Change drivers" })).toBeInTheDocument()
  expect(screen.getByRole("region", { name: "Recurring payments" })).toHaveTextContent("Gym Club")
  expect(calls.filter((u) => u.startsWith("/api/financial/ledger-trends-view?"))).toHaveLength(1)
  expect(calls.some((u) => u.startsWith("/api/financial/ledger?"))).toBe(false)
  expect(calls).toHaveLength(1)
})

it("reads every payment for the download, then downloads the browser's own comparison", async () => {
  const created = vi.fn((blob: Blob) => (void blob, "blob:trends"))
  URL.createObjectURL = created as unknown as typeof URL.createObjectURL
  URL.revokeObjectURL = vi.fn()
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
  renderPage()
  fireEvent.click(await screen.findByRole("button", { name: "Download comparison and evidence" }))
  await waitFor(() => expect(click).toHaveBeenCalledTimes(1))
  expect(calls.filter((u) => u.startsWith("/api/financial/ledger?"))).toHaveLength(1)
  const payload = JSON.parse(await (created.mock.calls[0][0] as Blob).text())
  expect(payload.transactions).toHaveLength(
    fixture.rows.filter((r) => r.currency === "USD" && r.account_type !== "credit_card").length
  )
  expect(payload.totals).toEqual(fixture.scenarios[0].server.result!.totals)
  click.mockRestore()
})

it("calculates in the browser from every payment where the server cannot reproduce the rows", async () => {
  server.unavailable = true
  renderPage()
  const changed = await screen.findByRole("region", { name: "What changed" })
  const debit = fixture.scenarios[0].server.result!.totals.find((t) => t.direction === "debit")!
  expect(within(changed).getByRole("heading", { name: "Money out" }).closest("article")).toHaveTextContent(
    `Later · ${debit.afterCount} payments`
  )
  expect(calls.filter((u) => u.startsWith("/api/financial/ledger?"))).toHaveLength(1)
})

it("never shows payments held over from another scope as this scope's figures", async () => {
  // Every payment for the whole case is already read (another page, or a download); the scope then narrows.
  const client = new QueryClient()
  client.setQueryData(["financial-ledger", CASE, {}], {
    case_id: CASE,
    total: fixture.rows.length,
    transactions: fixture.rows,
  })
  renderPage(client)
  await screen.findByRole("region", { name: "What changed" })
  expect(calls).toHaveLength(0)
  act(() => useInvestigationScopeStore.getState().apply(CASE, { startDate: "2021-01-01" }))
  await waitFor(() =>
    expect(calls.some((u) => u.startsWith("/api/financial/ledger-trends-view?") && u.includes("start_date=2021-01-01"))).toBe(true)
  )
  expect(calls.some((u) => u.startsWith("/api/financial/ledger?"))).toBe(false)
})

it("keeps the period controls on screen while a new choice is worked out", async () => {
  renderPage()
  await screen.findByRole("region", { name: "What changed" })
  const month = screen.getByLabelText("earlier month")
  fireEvent.change(month, { target: { value: "2020-12" } })
  expect(month).toBeInTheDocument()
  expect(screen.queryByRole("region", { name: "What changed" })).not.toBeInTheDocument()
  expect(screen.getByText("Working out trends for these periods…")).toBeInTheDocument()
  await waitFor(() =>
    expect(calls.filter((u) => u.startsWith("/api/financial/ledger-trends-view?"))).toHaveLength(2)
  )
})
