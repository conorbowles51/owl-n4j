/**
 * What this file is here to hold in place.
 *
 * The financial page reads two stores that are written independently and can
 * disagree: the relational ledger in Postgres, and the Neo4j graph. Before this
 * unit the page was the graph and nothing else, and it returned early on the
 * graph query before the tab strip was rendered at all.
 *
 * That is why most of these tests are about the empty and in-flight graph. A
 * case whose bank file has just been sent to the ledger has ledger rows and no
 * graph, and under the old arrangement that is exactly the case where the page
 * showed "No documentary transactions" and offered no way through to the rows
 * that do exist. The tests below fail if that early return ever comes back.
 */

import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { TooltipProvider } from "@/components/ui/tooltip"

import type { Transaction } from "../api"
import { useFinancialStore } from "../stores/financial.store"
import { FinancialPage } from "./FinancialPage"

const graph = vi.hoisted(() => ({ useTransactions: vi.fn() }))
const ledger = vi.hoisted(() => ({ useLedgerTransactions: vi.fn() }))
const runs = vi.hoisted(() => ({ useIngestionRuns: vi.fn() }))

const idleMutation = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }

vi.mock("../hooks/use-financial-data", () => ({
  useTransactions: graph.useTransactions,
  useFinancialCategories: () => ({ data: [] }),
  useFinancialEntities: () => ({ data: [] }),
  useCategorize: () => idleMutation,
  useBatchCategorize: () => idleMutation,
  useCreateCategory: () => idleMutation,
  useUpdateDetails: () => idleMutation,
  useUpdateAmount: () => idleMutation,
  useSetFromTo: () => idleMutation,
  useBatchSetFromTo: () => idleMutation,
  useBulkCorrect: () => idleMutation,
  useLinkSubTransaction: () => idleMutation,
  useUnlinkSubTransaction: () => idleMutation,
}))

vi.mock("../hooks/use-ledger-transactions", () => ({
  useLedgerTransactions: ledger.useLedgerTransactions,
}))

/*
 * Two components on this page read the run history: the notice above the
 * ledger and the attempts tab. Both call this hook, and unmocked it reaches
 * for a `QueryClientProvider` that this render does not supply and throws.
 * Each is wrapped in its own `ErrorBoundary`, which catches the throw, so
 * without this mock the page renders green while both are dead.
 */
vi.mock("../hooks/use-ingestion-runs", () => ({
  useIngestionRuns: runs.useIngestionRuns,
}))

function makeGraphRow(): Transaction {
  return {
    key: "tx-1",
    financial_view_mode: "transaction",
    financial_record_kind: "transaction",
    is_financial_event: true,
    is_evidence_backed_transaction: true,
    date: "2026-03-01",
    name: "Wire out",
    amount: 1200,
    currency: "USD",
    from_entity: { key: "e-1", name: "Northgate Holdings" },
    to_entity: { key: "e-2", name: "Marlowe Supply" },
  }
}

/** The graph query, in the three states the page used to branch on. */
function graphLoading() {
  graph.useTransactions.mockReturnValue({ data: undefined, isLoading: true })
}
function graphEmpty() {
  graph.useTransactions.mockReturnValue({
    data: { transactions: [], uses_legacy_financial_model: false },
    isLoading: false,
  })
}
function graphWithRows() {
  graph.useTransactions.mockReturnValue({
    data: {
      transactions: [makeGraphRow()],
      uses_legacy_financial_model: false,
    },
    isLoading: false,
  })
}

function ledgerEmpty() {
  ledger.useLedgerTransactions.mockReturnValue({
    data: { transactions: [], total: 0 },
    isPending: false,
    isError: false,
    error: null,
  })
}

/** No attempt recorded: the notice stays silent, the attempts tab says so. */
function runsEmpty() {
  runs.useIngestionRuns.mockReturnValue({
    data: { case_id: "case-1", runs: [], total: 0 },
    isPending: false,
    isError: false,
    error: null,
  })
}

/**
 * `TooltipProvider` is mounted app-wide in `app/providers.tsx`, so the page
 * always has one in production. Without it here the transaction table throws
 * into its error boundary, and a tab asserted to be showing the graph would in
 * fact be showing a caught error.
 */
function renderPage() {
  return render(
    <TooltipProvider>
      <MemoryRouter initialEntries={["/cases/case-1/financial"]}>
        <Routes>
          <Route path="/cases/:id/financial" element={<FinancialPage />} />
        </Routes>
      </MemoryRouter>
    </TooltipProvider>
  )
}

/** The toolbar's search box. Present only where the graph chrome is drawn. */
const GRAPH_SEARCH = "Search transactions..."

/**
 * Radix tab triggers change the tab on `mousedown`, verified in
 * `@radix-ui/react-tabs` (its trigger has no `onClick`). `fireEvent.click`
 * dispatches no `mousedown`, so it leaves the tab where it was and every
 * assertion after it silently describes the previous tab.
 */
function selectTab(name: string) {
  fireEvent.mouseDown(screen.getByRole("tab", { name }))
}

describe("FinancialPage", () => {
  beforeEach(() => {
    localStorage.clear()
    useFinancialStore.getState().reset()
    graph.useTransactions.mockReset()
    ledger.useLedgerTransactions.mockReset()
    runs.useIngestionRuns.mockReset()
    ledgerEmpty()
    runsEmpty()
  })

  /**
   * The order is load bearing. The first two tabs read Postgres and the last
   * three read the graph, and the two stores are written independently, so
   * which one is on screen is a fact about what you are looking at.
   */
  it("opens on the ledger, with the two ledger tabs first in the strip", () => {
    graphWithRows()
    renderPage()

    const tabs = screen.getAllByRole("tab")
    expect(tabs.map((t) => t.textContent)).toEqual([
      "Ledger",
      "Attempts",
      "Transactions",
      "Counterparties",
      "Trends",
    ])
    expect(tabs[0]).toHaveAttribute("aria-selected", "true")
  })

  it("mounts the ledger panel in the ledger tab", () => {
    graphWithRows()
    renderPage()

    expect(ledger.useLedgerTransactions).toHaveBeenCalledWith("case-1", undefined)
    expect(screen.getByText(/No admitted rows in the ledger/i)).toBeInTheDocument()
  })

  /**
   * The counts, filters and totals in the graph chrome are computed from graph
   * rows. Drawn above a ledger table they would read as a description of it.
   */
  it("keeps the graph chrome out of the ledger tab", () => {
    graphWithRows()
    renderPage()

    expect(screen.queryByPlaceholderText(GRAPH_SEARCH)).not.toBeInTheDocument()

    selectTab("Transactions")
    expect(screen.getByPlaceholderText(GRAPH_SEARCH)).toBeInTheDocument()
  })

  /** The case that used to be unreachable: ledger rows, no graph. */
  it("still reaches the ledger when the graph has no rows", () => {
    graphEmpty()
    renderPage()

    expect(screen.getAllByRole("tab")).toHaveLength(5)
    expect(screen.getByText(/No admitted rows in the ledger/i)).toBeInTheDocument()
  })

  it("still reaches the ledger while the graph query is in flight", () => {
    graphLoading()
    renderPage()

    expect(screen.getAllByRole("tab")).toHaveLength(5)
    expect(screen.getByText(/No admitted rows in the ledger/i)).toBeInTheDocument()
  })

  it("shows the graph's empty state inside the graph tab, not over the page", () => {
    graphEmpty()
    renderPage()

    expect(screen.queryByText("No documentary transactions")).not.toBeInTheDocument()

    selectTab("Transactions")
    expect(screen.getByText("No documentary transactions")).toBeInTheDocument()
    expect(screen.queryByPlaceholderText(GRAPH_SEARCH)).not.toBeInTheDocument()
  })
})

/**
 * The attempts tab is the record of what was loaded into the ledger. Its own
 * behaviour is covered in `IngestionRunsPanel.test.tsx`; what is asserted here
 * is only that the page reaches it, and reaches it without the graph.
 */
describe("FinancialPage, the attempts tab", () => {
  beforeEach(() => {
    localStorage.clear()
    useFinancialStore.getState().reset()
    graph.useTransactions.mockReset()
    ledger.useLedgerTransactions.mockReset()
    runs.useIngestionRuns.mockReset()
    ledgerEmpty()
    runsEmpty()
  })

  it("mounts the attempts panel when the tab is selected", () => {
    graphWithRows()
    renderPage()

    expect(
      screen.queryByText("No attempts recorded against this case")
    ).not.toBeInTheDocument()

    selectTab("Attempts")
    expect(
      screen.getByText("No attempts recorded against this case")
    ).toBeInTheDocument()
  })

  /**
   * The counts and filters in the graph chrome describe graph rows. Drawn above
   * the record of ingestion attempts they would read as a description of it.
   */
  it("keeps the graph chrome out of the attempts tab", () => {
    graphWithRows()
    renderPage()

    selectTab("Attempts")
    expect(screen.queryByPlaceholderText(GRAPH_SEARCH)).not.toBeInTheDocument()
  })

  /** Ledger rows and no graph: the record of what put them there is reachable. */
  it("reaches the attempts tab when the graph has no rows", () => {
    graphEmpty()
    renderPage()

    selectTab("Attempts")
    expect(
      screen.getByText("No attempts recorded against this case")
    ).toBeInTheDocument()
    expect(screen.queryByText("No documentary transactions")).not.toBeInTheDocument()
  })

  /**
   * The notice above the ledger and the attempts tab must share one fetch. That
   * holds only while every caller passes the case id and nothing else, so the
   * page is checked for a stray second argument here as well as in the panel.
   */
  it("reads the attempts with no window and no status filter", () => {
    graphWithRows()
    renderPage()

    selectTab("Attempts")
    for (const call of runs.useIngestionRuns.mock.calls) {
      expect(call).toEqual(["case-1"])
    }
  })
})
