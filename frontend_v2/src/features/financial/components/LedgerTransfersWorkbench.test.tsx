import { beforeEach } from "vitest"
import { useInvestigationScopeStore } from "../stores/investigation-scope"
beforeEach(() => useInvestigationScopeStore.getState().reset())
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { LedgerTransfersWorkbench } from "./LedgerTransfersWorkbench"
vi.mock("./LedgerSourceDialog", () => ({
  LedgerSourceDialog: ({ transactionId }: { transactionId: string }) => (
    <p>Source {transactionId}</p>
  ),
}))
afterEach(() => vi.restoreAllMocks())
const rows = [
  {
    key: "d",
    case_id: "case",
    account_id: "account-debit",
    source_document_id: "doc-d",
    amount_minor: "9007199254740993",
    currency: "GBP",
    direction: "debit",
    ordering_date: "2026-01-01",
    description: "Transfer out",
  },
  {
    key: "c",
    case_id: "case",
    account_id: "account-credit",
    source_document_id: "doc-c",
    amount_minor: "9007199254740993",
    currency: "GBP",
    direction: "credit",
    ordering_date: "2026-01-01",
    description: "Transfer in",
  },
  {
    key: "alternative",
    case_id: "case",
    account_id: "other-credit",
    source_document_id: "doc-alt",
    amount_minor: "9007199254740993",
    currency: "GBP",
    direction: "credit",
    ordering_date: "2026-01-01",
    description: "Alternative credit",
  },
]
const input = {
  case_id: "case",
  start_date: null,
  end_date: null,
  population: "working",
  tolerance_days: 3,
  snapshot_sha256: "a".repeat(64),
  applied: false,
  limitation: "Potential matches only",
  excluded_rows: 0,
  rows,
  date_unavailable_ids: [],
  candidates: [
    {
      debit_id: "d",
      credit_id: "c",
      currency: "GBP",
      amount_minor: "9007199254740993",
      outcome: "ambiguous",
      date_gap_days: 0,
      compared_date_field: "transaction_date",
    },
    {
      debit_id: "d",
      credit_id: "alternative",
      currency: "GBP",
      amount_minor: "9007199254740993",
      outcome: "ambiguous",
      date_gap_days: 0,
      compared_date_field: "transaction_date",
    },
  ],
}
function mount(data: unknown = input) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(data)))
  render(
    <QueryClientProvider client={new QueryClient()}>
      <LedgerTransfersWorkbench caseId="case" />
    </QueryClientProvider>
  )
  return fetch
}
it("shows exact ambiguous pairs and prevents reusing either source", async () => {
  const fetch = mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getByRole("button", { name: "Find possible transfers" })
  )
  await screen.findByLabelText("Pair transfer 1")
  expect(screen.getAllByText("90071992547409.93 GBP")).toHaveLength(2)
  fireEvent.click(screen.getByLabelText("Pair transfer 1"))
  expect(screen.getByLabelText("Pair transfer 2")).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Open debit source 1" }))
  expect(screen.getByText("Source d")).toBeInTheDocument()
  fireEvent.click(screen.getByLabelText("Pair transfer 1"))
  expect(screen.getByLabelText("Pair transfer 2")).toBeEnabled()
})
it("refuses candidates from another scope", async () => {
  mount({ ...input, case_id: "other" })
  fireEvent.click(
    screen.getByRole("button", { name: "Find possible transfers" })
  )
  expect(await screen.findByRole("alert")).toHaveTextContent("unavailable")
})
it("scope changes discard selected pairs and old results", async () => {
  mount()
  fireEvent.click(
    screen.getByRole("button", { name: "Find possible transfers" })
  )
  await screen.findByLabelText("Pair transfer 1")
  fireEvent.click(screen.getByLabelText("Pair transfer 1"))
  fireEvent.change(screen.getByLabelText("Transfer population"), {
    target: { value: "verified" },
  })
  expect(screen.queryByLabelText("Pair transfer 1")).not.toBeInTheDocument()
})
