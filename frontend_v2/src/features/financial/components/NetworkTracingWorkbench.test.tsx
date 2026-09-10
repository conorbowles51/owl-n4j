import { render, screen, fireEvent } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, expect, it, vi } from "vitest"
import { NetworkTracingWorkbench } from "./NetworkTracingWorkbench"
vi.mock("./RequestedCoveragePanel", () => ({
  RequestedCoveragePanel: () => null,
}))
afterEach(() => vi.restoreAllMocks())
const row = (
  key: string,
  account_id: string,
  direction: string,
  amount_minor: string
) => ({
  key,
  case_id: "case",
  account_id,
  direction,
  amount_minor,
  currency: "GBP",
  source_document_id: "source-" + key,
  ordering_date: "2026-01-01",
  description: key,
})
const scope = {
  case_id: "case",
  start_date: "2026-01-01",
  end_date: "2026-01-31",
  population: "working",
  tolerance_days: 3,
  snapshot_sha256: "a".repeat(64),
  applied: false,
  limitation: "Conditional",
  excluded_rows: 0,
  date_unavailable_ids: [],
  rows: [
    row("root", "a", "credit", "100"),
    row("debit", "a", "debit", "80"),
    row("credit", "b", "credit", "80"),
  ],
  candidates: [
    {
      debit_id: "debit",
      credit_id: "credit",
      currency: "GBP",
      amount_minor: "80",
      outcome: "resolved",
      date_gap_days: 0,
      compared_date_field: "transaction_date",
    },
  ],
  accounts: [
    { account_id: "a", currency: "GBP", label: "Account A" },
    { account_id: "b", currency: "GBP", label: "Account B" },
  ],
  network_row_limit: 300,
  network_limitation: "Forward assumptions",
}
it("requires explicit account openings, pairings and methods; excludes receiving credits from root choices", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(scope)))
  render(
    <QueryClientProvider client={new QueryClient()}>
      <NetworkTracingWorkbench caseId="case" />
    </QueryClientProvider>
  )
  expect(fetch).not.toHaveBeenCalled()
  for (const [label, value] of [
    ["Trace from date", "2026-01-01"],
    ["Trace through date", "2026-01-31"],
    ["Cross-account population", "working"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
  fireEvent.click(
    screen.getByRole("button", { name: "Load cross-account inputs" })
  )
  await screen.findByLabelText("Opening amount account 1")
  expect(screen.getByLabelText("Opening amount account 1")).toHaveValue("")
  expect(
    screen.getByLabelText("Allow backward transfer timing")
  ).not.toBeChecked()
  fireEvent.click(screen.getByLabelText("Allow backward transfer timing"))
  expect(screen.getByLabelText("Basis for backward timing")).toBeRequired()
  expect(
    screen.getByRole("button", { name: "Calculate cross-account scenario" })
  ).toBeDisabled()
  fireEvent.click(screen.getByLabelText("Trace transfer pair 1"))
  expect(
    screen.getByLabelText("Attributed deposit").querySelectorAll("option")
  ).toHaveLength(2)
  fireEvent.change(screen.getByLabelText("Trace from date"), {
    target: { value: "2026-01-02" },
  })
  expect(
    screen.queryByLabelText("Opening amount account 1")
  ).not.toBeInTheDocument()
})
