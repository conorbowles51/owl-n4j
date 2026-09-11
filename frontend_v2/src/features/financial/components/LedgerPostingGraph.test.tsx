import { beforeEach } from "vitest"
import { useInvestigationScopeStore } from "../stores/investigation-scope"
beforeEach(() => useInvestigationScopeStore.getState().reset())
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { LedgerPostingGraph } from "./LedgerPostingGraph"
vi.mock("./InvestigationFilters", () => ({ InvestigationFilters: () => null }))
vi.mock("./LedgerGraphCanvas", () => ({
  default: ({
    data,
    onNode,
    onSource,
  }: {
    data: { edges: { transaction_id: string; amount_minor: string }[] }
    onNode: (id: string) => void
    onSource: (id: string) => void
  }) => (
    <>
      <button onClick={() => onNode("a")}>Canvas account</button>
      {data.edges.map((edge) => (
        <button
          key={edge.transaction_id}
          onClick={() => onSource(edge.transaction_id)}
        >
          Source amount {edge.amount_minor}
        </button>
      ))}
    </>
  ),
}))
vi.mock("./LinkedPayments", () => ({
  LinkedPayments: ({ caseId, ids }: { caseId: string; ids: string[] }) => (
    <p data-testid="linked-payments">
      {caseId}/{ids.join(",")}
    </p>
  ),
}))
vi.mock("./LedgerSourceDialog", () => ({
  LedgerSourceDialog: ({ transactionId }: { transactionId: string }) => (
    <p>Source {transactionId}</p>
  ),
}))
afterEach(() => vi.restoreAllMocks())
const data = {
  case_id: "case",
  account_id: null,
  start_date: null,
  end_date: null,
  population: "working",
  snapshot_sha256: "a".repeat(64),
  applied: false,
  limitation: "Labels are not identities",
  excluded_rows: 0,
  nodes: [
    { id: "a", kind: "account", account_id: "account", label: "Account" },
    {
      id: "b",
      kind: "source_label",
      account_id: "account",
      label: "Unspecified counterparties",
    },
  ],
  edges: [
    {
      id: "row",
      transaction_id: "row",
      source: "a",
      target: "b",
      source_document_id: "doc",
      currency: "GBP",
      amount_minor: "9007199254740993",
      direction: "debit",
      ordering_date: "2026-01-01",
      description: "Source reading",
      proof_class: "p3",
    },
  ],
}
function mount(value: unknown = data) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async () => new Response(JSON.stringify(value)))
  render(
    <QueryClientProvider client={new QueryClient()}>
      <LedgerPostingGraph caseId="case" />
    </QueryClientProvider>
  )
  return fetch
}
it("loads current postings and source links with exact money", async () => {
  const fetch = mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Show connections" }))
  expect(
    await screen.findByRole("button", {
      name: "Source amount 9007199254740993",
    })
  ).toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", { name: "Source amount 9007199254740993" })
  )
  expect(screen.getByText("Source row")).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Canvas account" }))
  expect(screen.getByTestId("linked-payments")).toHaveTextContent("case/row")
})
it("refuses an edge to another account's source group", async () => {
  mount({
    ...data,
    nodes: [data.nodes[0], { ...data.nodes[1], account_id: "other" }],
  })
  fireEvent.click(screen.getByRole("button", { name: "Show connections" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("unavailable")
})
it("population changes remove the previous graph and source selection", async () => {
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Show connections" }))
  await screen.findByRole("button", { name: "Source amount 9007199254740993" })
  fireEvent.change(screen.getByLabelText("Payments to include"), {
    target: { value: "verified" },
  })
  expect(
    screen.queryByRole("button", { name: "Source amount 9007199254740993" })
  ).not.toBeInTheDocument()
})
