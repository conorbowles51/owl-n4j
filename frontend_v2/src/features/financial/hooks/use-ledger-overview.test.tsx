import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, expect, it, vi } from "vitest"
import { financialAPI } from "../api"
import { orderOverviewPanels, type OverviewPanels } from "../lib/overview-panels"
import { useLedgerOverview, useLedgerOverviewPanels } from "./use-ledger-overview"

const NO_CATEGORIES: string[] = []
const SCOPE = {}
vi.mock("../stores/investigation-scope", () => ({ useInvestigationScope: () => [SCOPE, vi.fn()] }))
vi.mock("./use-payment-categories", () => ({ usePaymentCategory: () => [NO_CATEGORIES, vi.fn()] }))
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const panels = (accounts: string[]): OverviewPanels => ({
  case_id: "case",
  complete: true,
  categories: [],
  totals: {
    payments: 0,
    inventory: { accounts: accounts.map((label, index) => ({ id: String(index), label, currencies: [] })), banks: ["b", "B", "a"],
      currencies: ["USD", "EUR"], first: null, last: null, undated: 0, unknown_banks: 0, unidentified_counterparties: 0 },
    groups: [],
    unreadable: 0,
  },
  connections: { payments: 0, groups: [{ group: "USD:bank" }, { group: "EUR:card" }] as OverviewPanels["connections"]["groups"] },
  comparisons: { pairs: 0, keys: [] },
})

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

// The Overview stays mounted behind other tabs. A name or category saved there patches the ledger's rows and only
// marks the Overview's figures out of date (refetchType "none"): they must be fetched again when it is shown.
it.each([
  ["panels", "getLedgerOverviewPanels", useLedgerOverviewPanels, "overview-panels"],
  ["top card", "getLedgerOverview", useLedgerOverview, "overview"],
] as const)("fetches the %s again when the Overview is shown after a save elsewhere", async (_name, method, hook, part) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 120000 } } })
  const api = vi.spyOn(financialAPI, method).mockResolvedValue(panels([]) as never)
  const view = renderHook(({ active }) => hook("case", active), { initialProps: { active: true }, wrapper: wrapper(client) })
  await waitFor(() => expect(view.result.current.isSuccess).toBe(true))
  expect(api).toHaveBeenCalledTimes(1)
  view.rerender({ active: false })
  await client.invalidateQueries({ queryKey: ["financial-ledger", "case"], refetchType: "none" })
  view.rerender({ active: false })
  expect(api).toHaveBeenCalledTimes(1) // not while hidden
  view.rerender({ active: true })
  await waitFor(() => expect(api).toHaveBeenCalledTimes(2))
  expect(client.getQueryState(["financial-ledger", "case", part, SCOPE, NO_CATEGORIES])?.isInvalidated).toBe(false)
  // Shown again with nothing changed: no further request.
  view.rerender({ active: false })
  view.rerender({ active: true })
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(api).toHaveBeenCalledTimes(2)
})

// A failed fetch marks a query out of date too: that must never turn into requests on every render.
it("asks once per showing when the server keeps failing, never in a loop", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 120000 } } })
  const api = vi.spyOn(financialAPI, "getLedgerOverviewPanels").mockRejectedValue(Error("down"))
  const view = renderHook(({ active }) => useLedgerOverviewPanels("case", active), { initialProps: { active: true }, wrapper: wrapper(client) })
  await waitFor(() => expect(view.result.current.isError).toBe(true))
  for (let i = 0; i < 3; i++) view.rerender({ active: true })
  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(api).toHaveBeenCalledTimes(1)
  view.rerender({ active: false })
  view.rerender({ active: true })
  await waitFor(() => expect(api).toHaveBeenCalledTimes(2))
  await waitFor(() => expect(view.result.current.isFetching).toBe(false))
  await new Promise((resolve) => setTimeout(resolve, 50))
  expect(api).toHaveBeenCalledTimes(2)
})

it("orders the server's lists as the page always has", () => {
  const ordered = orderOverviewPanels(panels(["Zeta", "alpha", "Beta"]))
  expect(ordered.totals.inventory.accounts.map((account) => account.label)).toEqual(["alpha", "Beta", "Zeta"])
  expect(ordered.totals.inventory.banks).toEqual(["B", "a", "b"])
  expect(ordered.totals.inventory.currencies).toEqual(["EUR", "USD"])
  expect(ordered.connections.groups.map((group) => group.group)).toEqual(["EUR:card", "USD:bank"])
})
