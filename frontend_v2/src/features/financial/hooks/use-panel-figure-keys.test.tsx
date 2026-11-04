import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { afterEach, expect, it, vi } from "vitest"
import { financialAPI, type LedgerTransaction } from "../api"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import {
  connectionGroups,
  countFigures,
  figureKeys,
  unnamedFigureId,
  type OverviewPanels,
  type PanelFigure,
} from "../lib/overview-panels"
import { MoneyConnectionsView } from "../components/InvestigatorFollowMoney"
import { useLedgerOverviewPanels, usePanelFigureKeys } from "./use-ledger-overview"

const NO_CATEGORIES: string[] = []
const SCOPE = {}
vi.mock("../stores/investigation-scope", () => ({ useInvestigationScope: () => [SCOPE, vi.fn()] }))
vi.mock("./use-payment-categories", () => ({ usePaymentCategory: () => [NO_CATEGORIES, vi.fn()] }))
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const payment = (key: string, fields: Partial<LedgerTransaction>): LedgerTransaction =>
  ({ ...paymentFixture, key, currency: "USD", account_type: "checking", amount_minor: "100",
    counterparty_link: null, ...fields }) as LedgerTransaction
const rows = [
  payment("in", { direction: "credit", from_name: "Ana", to_name: "Owner", amount_minor: "300" }),
  payment("in2", { direction: "credit", from_name: "Ana", to_name: "Owner", amount_minor: "5" }),
  payment("out", { direction: "debit", from_name: "Owner", to_name: "Ana", amount_minor: "120" }),
  payment("tax", { direction: "debit", from_name: "Owner", to_name: "", counterparty_raw: null, description: "C20 IVA COM" }),
  payment("card", { direction: "debit", from_name: "Owner", to_name: "Shop", account_type: "credit_card", currency: "MXN" }),
]
const groups = connectionGroups(rows)
const whole = (keysOf = groups): OverviewPanels => ({
  case_id: "case",
  complete: true,
  categories: [],
  totals: { payments: rows.length, inventory: { accounts: [], banks: [], currencies: [], first: null, last: null,
    undated: 0, unknown_banks: 0, unidentified_counterparties: 0 }, groups: [], unreadable: 0 },
  connections: { payments: rows.length, groups: keysOf },
  comparisons: { pairs: 1, keys: ["in", "out"] },
})
const figuresOf = (panels: OverviewPanels) => ({
  ...panels,
  connections: { ...panels.connections, groups: countFigures(panels.connections.groups) },
  comparisons: { pairs: panels.comparisons.pairs, count: panels.comparisons.keys.length },
})
function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

// Every figure the panel draws: its count is the length of its key list, and opening it finds exactly that list.
it("counts each key list and finds every figure's keys again from the whole panels", () => {
  const figures = countFigures(groups)
  let seen = 0
  for (const [index, group] of groups.entries()) {
    const drawn = figures[index]
    expect(drawn).not.toHaveProperty("names.0.credit.keys")
    expect(JSON.stringify(drawn)).not.toContain('"keys"')
    const check = (figure: PanelFigure, keys: string[], count: number) => {
      expect(count).toBe(keys.length)
      expect(figureKeys(whole(), figure)).toEqual(keys)
      seen += 1
    }
    group.names.forEach((name, n) => {
      check({ list: "credit", group: group.group, id: name.id }, name.credit.keys, drawn.names[n].credit.count)
      check({ list: "debit", group: group.group, id: name.id }, name.debit.keys, drawn.names[n].debit.count)
    })
    group.accounts.forEach((account, n) =>
      check({ list: "account", group: group.group, id: account.id }, account.keys, drawn.accounts[n].count))
    group.unnamed.forEach((item, n) =>
      check({ list: "unnamed", group: group.group, id: unnamedFigureId(item) }, item.keys, drawn.unnamed[n].count))
  }
  expect(seen).toBeGreaterThanOrEqual(7)
  expect(figureKeys(whole(), { list: "comparisons" })).toEqual(["in", "out"])
  expect(figureKeys(whole(), { list: "account", group: "EUR:bank", id: "x" })).toBeNull()
})

// The Overview asks for the counted answer only; the whole answer (the key lists, 2.5 of 2.9 MB on d5b330d1) is
// read when a figure is opened.
it("draws the Overview's panels without reading any key list", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const counted = vi.spyOn(financialAPI, "getLedgerOverviewPanelFigures").mockResolvedValue(figuresOf(whole()) as never)
  const keyed = vi.spyOn(financialAPI, "getLedgerOverviewPanels").mockResolvedValue(whole())
  const view = renderHook(() => useLedgerOverviewPanels("case"), { wrapper: wrapper(client) })
  await waitFor(() => expect(view.result.current.isSuccess).toBe(true))
  expect(counted).toHaveBeenCalledTimes(1)
  expect(keyed).not.toHaveBeenCalled()
  expect(view.result.current.data?.connections.groups.map((group) => group.group)).toEqual(["MXN:card", "USD:bank"])
})

it("reads the whole panels on the first open only, and opens exactly the figure's payments", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const keyed = vi.spyOn(financialAPI, "getLedgerOverviewPanels").mockResolvedValue(whole())
  const view = renderHook(() => usePanelFigureKeys("case"), { wrapper: wrapper(client) })
  const ana = { list: "credit", group: "USD:bank", id: "name:Ana" } as const
  await expect(view.result.current(ana, 2)).resolves.toEqual(["in", "in2"])
  await expect(view.result.current({ list: "comparisons" }, 2)).resolves.toEqual(["in", "out"])
  expect(keyed).toHaveBeenCalledTimes(1)
  // A write refreshes the case's ledger: the next open reads the whole panels again.
  await client.invalidateQueries({ queryKey: ["financial-ledger", "case"] })
  await expect(view.result.current(ana, 2)).resolves.toEqual(["in", "in2"])
  expect(keyed).toHaveBeenCalledTimes(2)
})

it("never opens a list its drawn count contradicts: reads again, then refreshes the drawn figures", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const fewer = groups.map((group) => ({ ...group, names: group.names.map((name) => ({
    ...name, credit: { ...name.credit, keys: name.credit.keys.slice(0, 1) } })) }))
  const keyed = vi.spyOn(financialAPI, "getLedgerOverviewPanels").mockResolvedValue(whole(fewer))
  const refresh = vi.spyOn(client, "invalidateQueries")
  const view = renderHook(() => usePanelFigureKeys("case"), { wrapper: wrapper(client) })
  await expect(view.result.current({ list: "credit", group: "USD:bank", id: "name:Ana" }, 2)).resolves.toBeNull()
  expect(keyed).toHaveBeenCalledTimes(2)
  expect(refresh).toHaveBeenCalledWith({ queryKey: ["financial-ledger", "case", "overview-panel-figures"] })
  // Read again and now as drawn: opened.
  keyed.mockResolvedValue(whole())
  await expect(view.result.current({ list: "credit", group: "USD:bank", id: "name:Ana" }, 2)).resolves.toEqual(["in", "in2"])
})

it("draws every count from the figures and hands back the figure chosen", async () => {
  const onOpen = vi.fn()
  render(<MoneyConnectionsView payments={rows.length} groups={countFigures(groups)} onOpen={onOpen} />)
  const bank = await screen.findByLabelText("Connection currency and account type")
  act(() => fireEvent.change(bank, { target: { value: "USD:bank" } }))
  fireEvent.click(screen.getByText("2 payments · 3.05 USD").closest("button")!)
  expect(onOpen).toHaveBeenLastCalledWith({ list: "credit", group: "USD:bank", id: "name:Ana" }, "Payments from Ana")
  fireEvent.click(screen.getByText(/1 payment ·/).closest("button")!)
  expect(onOpen).toHaveBeenLastCalledWith({ list: "unnamed", group: "USD:bank", id: "debit:tax" }, expect.any(String))
  expect(screen.getByText("1 payments without an identified counterparty")).toBeInTheDocument()
})
