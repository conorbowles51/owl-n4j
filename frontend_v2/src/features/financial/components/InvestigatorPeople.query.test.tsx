/**
 * People & businesses shows its list of names and accounts from one server answer and reads every payment only
 * when a profile is opened (d5b330d1: every payment is 64 MB; the page took 22-64 s before the list showed while it
 * waited for them and for the account directory).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import fixture from "../lib/people-parity.fixture.json"
import { InvestigatorPeople } from "./InvestigatorPeople"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { useInvestigationScopeStore } from "../stores/investigation-scope"

const calls = vi.hoisted(() => [] as string[])
const server = vi.hoisted(() => ({ unavailable: false }))
const CASE = fixture.case_id
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(async (url: string) => {
    calls.push(url)
    if (url.startsWith("/api/financial/ledger-people-view?")) {
      if (server.unavailable) return { case_id: CASE, available: false, reason: "a date in year 0000" }
      const group = new URLSearchParams(url.split("?")[1]).get("group")
      const scenario = fixture.scenarios.find(
        (s) => (s.ask as { group?: string; categories?: string[] }).group === (group ?? undefined) &&
          !(s.ask as { categories?: string[] }).categories
      )!
      return { case_id: CASE, available: true, ...scenario.server }
    }
    if (url.startsWith("/api/financial/ledger?"))
      return { case_id: CASE, total: fixture.rows.length, transactions: fixture.rows }
    if (url.startsWith("/api/financial/account-parties?"))
      return fixture.directory
    if (url.startsWith("/api/financial/judgements")) return {}
    throw Error(`unexpected request ${url}`)
  }),
}))
vi.mock("../hooks/use-financial-finding-index", () => ({
  useFinancialFindingIndex: () => ({ data: [] }),
}))
vi.mock("./InvestigationWorkspaceParts", async (original) => ({
  ...(await original<typeof import("./InvestigationWorkspaceParts")>()),
  WorkspaceScope: () => null,
}))
vi.mock("./AccountConsolidation", () => ({ AccountConsolidation: () => null }))
vi.mock("./AccountOwnershipReview", () => ({ AccountOwnershipReview: () => null }))
vi.mock("./AccountHistory", () => ({ AccountHistory: () => null }))
vi.mock("./LedgerCounterpartiesAnalysis", () => ({ LedgerCounterpartiesAnalysis: () => null }))
vi.mock("./LedgerRowBrowser", () => ({
  LedgerRowBrowser: ({ transactions }: { transactions: unknown[] }) => (
    <p>Payment table with {transactions.length} payments</p>
  ),
}))

afterEach(() => {
  cleanup()
  calls.length = 0
  server.unavailable = false
  useInvestigationScopeStore.getState().reset()
  useFinancialDraftStore.setState({ drafts: {} })
})

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <InvestigatorPeople caseId={CASE} />
      </MemoryRouter>
    </QueryClientProvider>
  )

/** The card whose heading is exactly `name` (the fixture also has "  Shop  ", which a role query reads as "Shop"). */
const findCard = async (name: string) => {
  let card: HTMLElement | undefined
  await waitFor(() => {
    card = screen.getAllByRole("heading").find((h) => h.textContent === name)?.closest("button") ?? undefined
    expect(card).toBeDefined()
  })
  return card!
}
const hasCard = (name: string) => screen.queryAllByRole("heading").some((h) => h.textContent === name)

const shop = () => fixture.scenarios[0].server.profiles!.find((p) => p.id === "name:Shop")!

it("shows the list from one request, without reading every payment or the directory", async () => {
  renderPage()
  const card = await findCard("Shop")
  expect(card).toHaveTextContent(`${shop().payments} matching payments`)
  expect(card).toHaveTextContent(`${shop().totals!.payments} transactions`)
  expect(screen.getByRole("heading", { name: "Ana Ruiz" })).toBeInTheDocument()
  expect(screen.getAllByText("Counterparty not identified")).toHaveLength(2)
  expect(calls.filter((u) => u.startsWith("/api/financial/ledger-people-view?"))).toHaveLength(1)
  expect(calls.some((u) => u.startsWith("/api/financial/ledger?"))).toBe(false)
  expect(calls.some((u) => u.startsWith("/api/financial/account-parties?"))).toBe(false)
  expect(calls).toHaveLength(1)
})

it("reads every payment and the directory when a profile is opened", async () => {
  renderPage()
  fireEvent.click(await findCard("Shop"))
  expect(await screen.findByText(`Payment table with ${shop().payments} payments`)).toBeInTheDocument()
  expect(calls.filter((u) => u.startsWith("/api/financial/ledger?"))).toHaveLength(1)
  expect(calls.filter((u) => u.startsWith("/api/financial/account-parties?"))).toHaveLength(1)
  fireEvent.click(screen.getByRole("button", { name: "Back to names and accounts" }))
  expect(await findCard("Shop")).toBeInTheDocument()
})

it("groups every payment in the browser where the server cannot reproduce the rows", async () => {
  server.unavailable = true
  renderPage()
  const card = await findCard("Shop")
  expect(card).toHaveTextContent(`${shop().payments} matching payments`)
  expect(calls.filter((u) => u.startsWith("/api/financial/ledger?"))).toHaveLength(1)
})

it("keeps the controls on screen while a currency is worked out, then shows its cards", async () => {
  renderPage()
  await findCard("Shop")
  const currency = screen.getByLabelText("Profile currency and account type")
  fireEvent.change(currency, { target: { value: "USD:card" } })
  await waitFor(() =>
    expect(calls.some((u) => u.startsWith("/api/financial/ledger-people-view?") && u.includes("group=USD%3Acard"))).toBe(true)
  )
  expect(await findCard("Hotel")).toBeInTheDocument()
  expect(hasCard("Shop")).toBe(false)
  expect(screen.getByLabelText("Profile currency and account type")).toBeInTheDocument()
  expect(calls.some((u) => u.startsWith("/api/financial/ledger?"))).toBe(false)
})
