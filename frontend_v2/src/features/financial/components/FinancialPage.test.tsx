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

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { proofStanding } from "@/test/proof-standing-fixture"
import { TooltipProvider } from "@/components/ui/tooltip"

import type { LedgerTransaction, Transaction } from "../api"
import { useFinancialStore } from "../stores/financial.store"
import { FinancialPage } from "./FinancialPage"

const graph = vi.hoisted(() => ({ useTransactions: vi.fn() }))
const ledger = vi.hoisted(() => ({ useLedgerTransactions: vi.fn() }))
const runs = vi.hoisted(() => ({ useIngestionRuns: vi.fn() }))
const adjudication = vi.hoisted(() => ({ useRowAdjudication: vi.fn() }))
const standing = vi.hoisted(() => ({ useProofStanding: vi.fn() }))
const decisions = vi.hoisted(() => ({ useCaseDecisions: vi.fn() }))

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

// Control run-history results independently of the ledger and graph fixtures.
vi.mock("../hooks/use-ingestion-runs", () => ({
  useIngestionRuns: runs.useIngestionRuns,
}))

// Keep adjudication outcomes deterministic while checking dialog lifetime.
vi.mock("../hooks/use-row-adjudication", () => ({
  useRowAdjudication: adjudication.useRowAdjudication,
}))

// Decision-log rendering has its own tests; this suite checks page placement.
vi.mock("../hooks/use-case-decisions", () => ({
  useCaseDecisions: decisions.useCaseDecisions,
}))

vi.mock("../hooks/use-proof-standing", () => ({
  useProofStanding: standing.useProofStanding,
}))

beforeEach(() => {
  standing.useProofStanding.mockReturnValue({
    data: proofStanding(),
    isPending: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  })
})

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

function makeLedgerRow(
  overrides: Partial<LedgerTransaction> = {}
): LedgerTransaction {
  return {
    key: "txn-1",
    case_id: "case-1",
    account_id: "acct-1",
    source_document_id: "doc-1",
    ingestion_run_id: "run-1",
    statement_period_id: null,
    ref_id: "ref-1",
    row_index: 0,
    amount_minor: 123456,
    currency: "USD",
    direction: "debit",
    running_balance_minor: null,
    transaction_date: "2024-03-01",
    posted_date: null,
    value_date: null,
    effective_date: null,
    ordering_date: "2024-03-01",
    ordering_date_source: "transaction",
    description: "CARD PAYMENT",
    counterparty_raw: null,
    transaction_type: null,
    bank_reference: null,
    proof_class: "p2",
    extraction_layer: 1,
    ledger_status: "admitted",
    quarantine_reason: null,
    superseded_by_id: null,
    ...overrides,
  }
}

function ledgerEmpty() {
  ledger.useLedgerTransactions.mockReturnValue({
    data: { transactions: [], total: 0 },
    isPending: false,
    isError: false,
    error: null,
  })
}

/**
 * One mock serves both ledger panels, and only one of them is mounted at a
 * time, so what this returns is whatever the tab on screen is reading.
 */
function ledgerWithRows(rows: LedgerTransaction[]) {
  ledger.useLedgerTransactions.mockReturnValue({
    data: { transactions: rows, total: rows.length },
    isPending: false,
    isError: false,
    error: null,
  })
}

/** Idle, and never asked to do anything. See the mock's comment. */
function adjudicationIdle() {
  adjudication.useRowAdjudication.mockReturnValue({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    data: undefined,
    error: null,
  })
}

/** Nothing decided: the decisions tab says so rather than drawing a table. */
function decisionsEmpty() {
  decisions.useCaseDecisions.mockReturnValue({
    data: {
      case_id: "case-1",
      decisions: [],
      total: 0,
      limit: 100,
      offset: 0,
      truncated: false,
    },
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
// Real auxiliary panels need the same query provider as the application.
// Keep it stable across rerenders, but isolate its cache between tests.
let pageQueries: QueryClient
beforeEach(() => {
  pageQueries = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
})

function pageTree() {
  return (
    <QueryClientProvider client={pageQueries}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/cases/case-1/financial"]}>
          <Routes>
            <Route path="/cases/:id/financial" element={<FinancialPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  )
}

function renderPage() {
  return render(pageTree())
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
    adjudication.useRowAdjudication.mockReset()
    ledgerEmpty()
    runsEmpty()
    adjudicationIdle()
  })

  /**
   * The order is load bearing. The first four tabs read Postgres and the last
   * three read the graph, and the two stores are written independently, so
   * which one is on screen is a fact about what you are looking at.
   *
   * "Held out" sits directly after "Ledger" because the two are one read
   * against two populations: what this case's totals count, and what they
   * leave out.
   *
   * "Decisions" is last of the four because it is the only one that is not a
   * view of the ledger's present contents. The three before it answer what the
   * case holds now; it answers who moved any of it and on what grounds, and it
   * outlives its subjects.
   */
  it("opens on the ledger, with statement review alongside the ledger tabs", () => {
    graphWithRows()
    renderPage()

    const tabs = screen.getAllByRole("tab")
    expect(tabs.map((t) => t.textContent)).toEqual([
      "Ledger",
      "Statements",
      "Held out",
      "Attempts",
      "Decisions",
      "Transactions",
      "Counterparties",
      "Posting graph",
      "Transfers",
      "Patterns",
      "Case context",
      "Conditional tracing",
      "Trends",
    ])
    expect(tabs[0]).toHaveAttribute("aria-selected", "true")
  })

  it("opens statement checks and coverage without waiting for graph results", () => {
    graphLoading()
    renderPage()
    selectTab("Statements")
    expect(
      screen.getByRole("button", { name: "Check statement balances" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Check statement coverage" })
    ).toBeInTheDocument()
    expect(
      screen.queryByText(/No admitted rows in the ledger/i)
    ).not.toBeInTheDocument()
  })

  it("mounts the ledger panel in the ledger tab", () => {
    graphWithRows()
    renderPage()

    expect(ledger.useLedgerTransactions).toHaveBeenCalledWith("case-1", {})
    expect(
      screen.getByText(/No admitted rows in the ledger/i)
    ).toBeInTheDocument()
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
    expect(screen.queryByPlaceholderText(GRAPH_SEARCH)).not.toBeInTheDocument()
    fireEvent.click(
      screen.getByRole("button", { name: "Financial intelligence" })
    )
    expect(
      screen.getByPlaceholderText("Search financial intelligence...")
    ).toBeInTheDocument()
  })

  /** The case that used to be unreachable: ledger rows, no graph. */
  it("opens the source-linked pattern review screen", () => {
    graphEmpty()
    renderPage()
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Patterns" }), { button: 0, ctrlKey: false })
    expect(screen.getByRole("heading", { name: "Patterns to investigate" })).toBeInTheDocument()
  })

  it("still reaches the ledger when the graph has no rows", () => {
    graphEmpty()
    renderPage()

    expect(screen.getAllByRole("tab")).toHaveLength(13)
    expect(
      screen.getByText(/No admitted rows in the ledger/i)
    ).toBeInTheDocument()
  })

  it("still reaches the ledger while the graph query is in flight", () => {
    graphLoading()
    renderPage()

    expect(screen.getAllByRole("tab")).toHaveLength(13)
    expect(
      screen.getByText(/No admitted rows in the ledger/i)
    ).toBeInTheDocument()
  })

  it("shows the graph's empty state inside the graph tab, not over the page", () => {
    graphEmpty()
    renderPage()

    expect(
      screen.queryByText("No documentary transactions")
    ).not.toBeInTheDocument()

    selectTab("Transactions")
    fireEvent.click(
      screen.getByRole("button", { name: "Financial intelligence" })
    )
    expect(screen.getByText("No financial intelligence")).toBeInTheDocument()
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
    adjudication.useRowAdjudication.mockReset()
    ledgerEmpty()
    runsEmpty()
    adjudicationIdle()
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
    expect(
      screen.queryByText("No documentary transactions")
    ).not.toBeInTheDocument()
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

/**
 * The decisions tab shows the record of what was decided about this case's
 * evidence and on what grounds. Its own behaviour is covered in
 * `DecisionsPanel.test.tsx`; what is asserted here is that the page reaches it,
 * that it reaches it without the graph, and that the panel is mounted only when
 * the tab is on screen.
 */
describe("FinancialPage, the decisions tab", () => {
  beforeEach(() => {
    localStorage.clear()
    useFinancialStore.getState().reset()
    graph.useTransactions.mockReset()
    ledger.useLedgerTransactions.mockReset()
    runs.useIngestionRuns.mockReset()
    adjudication.useRowAdjudication.mockReset()
    decisions.useCaseDecisions.mockReset()
    ledgerEmpty()
    runsEmpty()
    decisionsEmpty()
    adjudicationIdle()
  })

  it("mounts the decisions panel when the tab is selected", () => {
    graphWithRows()
    renderPage()

    expect(
      screen.queryByText("Nothing has been decided about this case")
    ).not.toBeInTheDocument()

    selectTab("Decisions")
    expect(
      screen.getByText("Nothing has been decided about this case")
    ).toBeInTheDocument()
  })

  /**
   * The counts and filters in the graph chrome describe graph rows. Drawn above
   * the record of decisions they would read as a description of it.
   */
  it("keeps the graph chrome out of the decisions tab", () => {
    graphWithRows()
    renderPage()

    selectTab("Decisions")
    expect(screen.queryByPlaceholderText(GRAPH_SEARCH)).not.toBeInTheDocument()
  })

  /**
   * Ledger rows and no graph. This is the case a decision is most likely to
   * have been taken on, because quarantining a row is one of the things that
   * keeps it out of the graph in the first place.
   */
  it("reaches the decisions tab when the graph has no rows", () => {
    graphEmpty()
    renderPage()

    selectTab("Decisions")
    expect(
      screen.getByText("Nothing has been decided about this case")
    ).toBeInTheDocument()
    expect(
      screen.queryByText("No documentary transactions")
    ).not.toBeInTheDocument()
  })

  /**
   * The panel is handed the case and nothing else. A second argument, even
   * `{}`, would open a second cache entry against the same page, for the reason
   * `use-case-decisions.ts` records.
   */
  it("reads the decisions with no filters and no window", () => {
    graphWithRows()
    renderPage()

    selectTab("Decisions")
    for (const call of decisions.useCaseDecisions.mock.calls) {
      expect(call).toEqual(["case-1"])
    }
  })
})

/**
 * The held-out tab shows the rows a case's totals leave out. Its own behaviour
 * is covered in `QuarantinePanel.test.tsx`; what is asserted here is that the
 * page reaches it, that it reaches it without the graph, and that it asks for
 * the quarantined population rather than the ledger's default one.
 */
describe("FinancialPage, the held-out tab", () => {
  beforeEach(() => {
    localStorage.clear()
    useFinancialStore.getState().reset()
    graph.useTransactions.mockReset()
    ledger.useLedgerTransactions.mockReset()
    runs.useIngestionRuns.mockReset()
    adjudication.useRowAdjudication.mockReset()
    ledgerEmpty()
    runsEmpty()
    adjudicationIdle()
  })

  it("mounts the quarantine panel when the tab is selected", () => {
    graphWithRows()
    renderPage()

    expect(
      screen.queryByText(/No rows are currently quarantined/i)
    ).not.toBeInTheDocument()

    selectTab("Held out")
    expect(
      screen.getByText(/No rows are currently quarantined/i)
    ).toBeInTheDocument()
  })

  /**
   * The one claim this tab cannot get wrong. Every sentence on it is about
   * quarantine, and the ledger read defaults to `admitted` when no status is
   * sent, so a missing status here would put admitted rows under copy saying
   * they are being held out of the totals.
   */
  it("asks the ledger for the quarantined rows", () => {
    graphWithRows()
    renderPage()

    selectTab("Held out")
    expect(ledger.useLedgerTransactions).toHaveBeenCalledWith("case-1", {
      ledgerStatus: "quarantined",
    })
  })

  /** The counts and filters in the graph chrome describe graph rows. */
  it("keeps the graph chrome out of the held-out tab", () => {
    graphWithRows()
    renderPage()

    selectTab("Held out")
    expect(screen.queryByPlaceholderText(GRAPH_SEARCH)).not.toBeInTheDocument()
  })

  /** Ledger rows and no graph: what the totals exclude is still reachable. */
  it("reaches the held-out tab when the graph has no rows", () => {
    graphEmpty()
    renderPage()

    selectTab("Held out")
    expect(
      screen.getByText(/No rows are currently quarantined/i)
    ).toBeInTheDocument()
    expect(
      screen.queryByText("No documentary transactions")
    ).not.toBeInTheDocument()
  })
})

/**
 * Where the dialog is mounted, and why it has to be there.
 *
 * The change a person asks for on a row is answered once, in the response to
 * that one write, and the answer includes whether the change rescued a
 * reconciled period. Nothing else on this screen says it. So the dialog has to
 * outlive two things that happen the moment a change succeeds: the row leaving
 * the list it was clicked in, and the person moving off the tab that list was
 * on. Both are tested below by taking the row away underneath an open dialog,
 * which is what the ledger invalidation does in production.
 *
 * A dialog owned by either panel fails the first of these, because both panels
 * return an empty state before rendering anything below it. A dialog rendered
 * inside `TabsContent` fails the second, because only the active tab's content
 * is mounted.
 */
describe("FinancialPage, the row adjudication dialog", () => {
  beforeEach(() => {
    localStorage.clear()
    useFinancialStore.getState().reset()
    graph.useTransactions.mockReset()
    ledger.useLedgerTransactions.mockReset()
    runs.useIngestionRuns.mockReset()
    adjudication.useRowAdjudication.mockReset()
    runsEmpty()
    adjudicationIdle()
  })

  it("opens on the row whose action was pressed, from the ledger tab", () => {
    graphWithRows()
    ledgerWithRows([makeLedgerRow({ key: "txn-9" })])
    renderPage()

    fireEvent.click(screen.getByTestId("ledger-row-action"))

    expect(screen.getByTestId("adjudication-row")).toHaveAttribute(
      "data-row-key",
      "txn-9"
    )
  })

  it("opens on the row whose action was pressed, from the held-out tab", () => {
    graphWithRows()
    ledgerWithRows([
      makeLedgerRow({
        key: "txn-4",
        ledger_status: "quarantined",
        quarantine_reason: "balance_break",
      }),
    ])
    renderPage()

    selectTab("Held out")
    fireEvent.click(screen.getByTestId("ledger-row-action"))

    expect(screen.getByTestId("adjudication-row")).toHaveAttribute(
      "data-row-key",
      "txn-4"
    )
  })

  /**
   * The list going empty is what a successful release looks like from this
   * page: the ledger reads are invalidated and the row is no longer in the
   * quarantined population. The panel is correct to show its empty state. The
   * dialog holding the only statement of what the change did must not go with
   * it.
   */
  it("stays open after its row leaves the list underneath it", () => {
    graphWithRows()
    ledgerWithRows([
      makeLedgerRow({ key: "txn-4", ledger_status: "quarantined" }),
    ])
    const { rerender } = renderPage()

    selectTab("Held out")
    fireEvent.click(screen.getByTestId("ledger-row-action"))
    expect(screen.getByTestId("adjudication-row")).toBeInTheDocument()

    ledgerEmpty()
    rerender(pageTree())

    expect(
      screen.getByText(/No rows are currently quarantined/i)
    ).toBeInTheDocument()
    expect(screen.getByTestId("adjudication-row")).toHaveAttribute(
      "data-row-key",
      "txn-4"
    )
  })

  /**
   * The same guard on the other side. Setting a row aside takes it out of the
   * admitted population, so the ledger tab empties underneath the dialog in
   * exactly the way the held-out tab does.
   *
   * There is no companion test for a change of tab while the dialog is open,
   * because there is no such thing: the dialog is modal, so Radix hides the
   * rest of the document from the accessibility tree and the tab strip cannot
   * be reached behind it. Mounting outside `Tabs` is still what the other six
   * dialogs on this page do, and it costs nothing to match them.
   */
  it("stays open after its row leaves the ledger underneath it", () => {
    graphWithRows()
    ledgerWithRows([makeLedgerRow({ key: "txn-9" })])
    const { rerender } = renderPage()

    fireEvent.click(screen.getByTestId("ledger-row-action"))
    expect(screen.getByTestId("adjudication-row")).toBeInTheDocument()

    ledgerEmpty()
    rerender(pageTree())

    expect(
      screen.getByText(/No admitted rows in the ledger/i)
    ).toBeInTheDocument()
    expect(screen.getByTestId("adjudication-row")).toHaveAttribute(
      "data-row-key",
      "txn-9"
    )
  })

  it("closes only when the person closes it", () => {
    graphWithRows()
    ledgerWithRows([makeLedgerRow({ key: "txn-9" })])
    renderPage()

    fireEvent.click(screen.getByTestId("ledger-row-action"))
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }))

    expect(screen.queryByTestId("adjudication-row")).not.toBeInTheDocument()
  })
})

it("shows the classification census even when both the graph and admitted ledger are empty", () => {
  useFinancialStore.getState().reset()
  graphEmpty()
  ledgerEmpty()
  runsEmpty()
  adjudicationIdle()
  renderPage()
  expect(screen.getByTestId("proof-standing-totals")).toHaveTextContent(
    "5 financial source documents"
  )
  expect(standing.useProofStanding).toHaveBeenCalledWith("case-1")
  expect(screen.getByTestId("proof-standing-panel")).toBeInTheDocument()
  expect(
    screen.getByRole("region", { name: "Duplicate candidates" })
  ).toBeInTheDocument()
})

vi.mock("../hooks/use-duplicate-candidates", () => ({
  useDuplicateCandidates: () => ({
    isPending: true,
    isFetching: false,
    refetch: vi.fn(),
  }),
}))

describe("FinancialPage authoritative Trends", () => {
  beforeEach(() => {
    localStorage.clear()
    useFinancialStore.getState().reset()
    ledgerEmpty()
    runsEmpty()
    adjudicationIdle()
  })
  it.each(["empty", "loading"])(
    "reaches ledger trends with a %s graph",
    (state) => {
      if (state === "empty") graphEmpty()
      else graphLoading()
      renderPage()
      selectTab("Trends")
      expect(
        screen.getByRole("region", { name: "Authoritative ledger trends" })
      ).toBeInTheDocument()
      expect(
        screen.getByRole("region", { name: "Working ledger totals" })
      ).toBeInTheDocument()
      expect(
        screen.queryByPlaceholderText(GRAPH_SEARCH)
      ).not.toBeInTheDocument()
      expect(screen.queryByText("Money Out")).not.toBeInTheDocument()
    }
  )
  it("separates intelligence and always permits returning to ledger analysis", () => {
    graphEmpty()
    renderPage()
    selectTab("Trends")
    fireEvent.click(
      screen.getByRole("button", { name: "Financial intelligence" })
    )
    expect(
      screen.queryByRole("region", { name: "Authoritative ledger trends" })
    ).not.toBeInTheDocument()
    expect(
      screen.getByText(/do not reflect ledger corrections/)
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Ledger postings" }))
    expect(
      screen.getByRole("region", { name: "Authoritative ledger trends" })
    ).toBeInTheDocument()
  })
})

describe("FinancialPage authoritative Transactions", () => {
  beforeEach(() => {
    localStorage.clear()
    useFinancialStore.getState().reset()
    ledgerEmpty()
    runsEmpty()
    adjudicationIdle()
  })
  it.each(["empty", "loading", "populated"])(
    "shows ledger transactions independently of a %s graph",
    (state) => {
      if (state === "empty") graphEmpty()
      else if (state === "loading") graphLoading()
      else graphWithRows()
      renderPage()
      selectTab("Transactions")
      expect(
        screen.getByText(/No admitted rows in the ledger/i)
      ).toBeInTheDocument()
      expect(
        screen.getByRole("region", { name: "Working ledger totals" })
      ).toBeInTheDocument()
      expect(
        screen.queryByPlaceholderText(GRAPH_SEARCH)
      ).not.toBeInTheDocument()
      expect(screen.queryByText("Money Out")).not.toBeInTheDocument()
    }
  )
  it("returns from intelligence to current ledger readings", () => {
    graphEmpty()
    renderPage()
    selectTab("Transactions")
    fireEvent.click(
      screen.getByRole("button", { name: "Financial intelligence" })
    )
    expect(
      screen.queryByText(/No admitted rows in the ledger/i)
    ).not.toBeInTheDocument()
    expect(
      screen.getByText(/do not reflect ledger corrections/)
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Ledger postings" }))
    expect(
      screen.getByText(/No admitted rows in the ledger/i)
    ).toBeInTheDocument()
  })
})

describe("FinancialPage authoritative Counterparties", () => {
  beforeEach(() => {
    localStorage.clear()
    useFinancialStore.getState().reset()
    ledgerEmpty()
    runsEmpty()
    adjudicationIdle()
  })
  it.each(["empty", "loading", "populated"])(
    "shows ledger transactions independently of a %s graph",
    (state) => {
      if (state === "empty") graphEmpty()
      else if (state === "loading") graphLoading()
      else graphWithRows()
      renderPage()
      selectTab("Counterparties")
      expect(
        screen.getByRole("region", {
          name: "Authoritative ledger counterparties",
        })
      ).toBeInTheDocument()
      expect(
        screen.getByRole("region", { name: "Working ledger totals" })
      ).toBeInTheDocument()
      expect(
        screen.queryByPlaceholderText(GRAPH_SEARCH)
      ).not.toBeInTheDocument()
      expect(screen.queryByText("Money Out")).not.toBeInTheDocument()
    }
  )
  it("returns from intelligence to current ledger readings", () => {
    graphEmpty()
    renderPage()
    selectTab("Counterparties")
    fireEvent.click(
      screen.getByRole("button", { name: "Financial intelligence" })
    )
    expect(
      screen.queryByRole("region", {
        name: "Authoritative ledger counterparties",
      })
    ).not.toBeInTheDocument()
    expect(
      screen.getByText(/do not reflect ledger corrections/)
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Ledger postings" }))
    expect(
      screen.getByRole("region", {
        name: "Authoritative ledger counterparties",
      })
    ).toBeInTheDocument()
  })
})
