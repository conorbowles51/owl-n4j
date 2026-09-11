import { beforeEach } from "vitest"
import { useInvestigationScopeStore } from "../stores/investigation-scope"
beforeEach(() => useInvestigationScopeStore.getState().reset())
import { render, screen, fireEvent } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, expect, it, vi } from "vitest"
import { FinancialCaseTimeline } from "./FinancialCaseTimeline"
vi.mock("./InvestigationFilters", () => ({ InvestigationFilters: () => null }))
vi.mock("./RequestedCoveragePanel", () => ({
  RequestedCoveragePanel: () => null,
}))
const ledger = {
  case_id: "case",
  account_id: null,
  start_date: null,
  end_date: null,
  population: "working",
  snapshot_sha256: "a".repeat(64),
  excluded_rows: 0,
  limitation: "Separate date bases",
  rows: [
    {
      key: "row",
      source_document_id: "source",
      account_id: "account",
      account_label: "Account A",
      chronology_date: "2026-01-01",
      chronology_basis: "statement_end_ordering_only",
      ordering_date: "2026-01-01",
      direction: "debit",
      amount_minor: "1234",
      currency: "GBP",
      proof_class: "p3",
      description: "Source payment",
    },
  ],
}
const event = {
  key: "event",
  date: "2026-01-01",
  name: "Meeting about purchase",
  type: "Meeting",
  time: null,
  amount: "999999",
  summary: "Statement by a witness",
  notes: null,
  connections: [],
}
afterEach(() => vi.restoreAllMocks())
function setup(events: unknown = { events: [event], count: 1, total: 1 }) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    if (String(input).includes("/api/timeline?") && events === null)
      throw Error("Offline")
    return new Response(
      JSON.stringify(
        String(input).includes("/ledger-timeline?") ? ledger : events
      )
    )
  })
  render(
    <QueryClientProvider client={new QueryClient()}>
      <FinancialCaseTimeline caseId="case" />
    </QueryClientProvider>
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Load payments and case events" })
  )
}
it("keeps context separate from exact ledger money and makes unknown dates explicit", async () => {
  setup()
  await screen.findByText("Source payment")
  expect(
    screen.getByText("Transaction date unknown — statement-end ordering only")
  ).toBeInTheDocument()
  expect(screen.getByText(/debit 12.34 GBP/)).toBeInTheDocument()
  expect(screen.queryByText(/999999/)).not.toBeInTheDocument()
  expect(
    screen.getByRole("button", {
      name: "Open case event Meeting about purchase",
    })
  ).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Timeline item type"), {
    target: { value: "posting" },
  })
  expect(
    screen.queryByText("Meeting about purchase · Meeting")
  ).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Timeline population"), {
    target: { value: "verified" },
  })
  expect(screen.queryByText("Source payment")).not.toBeInTheDocument()
})
it("shows unavailable events distinctly while preserving the ledger", async () => {
  setup(null)
  await screen.findByText("Source payment")
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Case events could not be loaded"
  )
})
it("marks a truncated case-event result as incomplete", async () => {
  setup({ events: [event], count: 1, total: 4, next_cursor: "more" })
  await screen.findByText("Source payment")
  expect(
    screen.getByText(/Case event results are incomplete/)
  ).toBeInTheDocument()
})
