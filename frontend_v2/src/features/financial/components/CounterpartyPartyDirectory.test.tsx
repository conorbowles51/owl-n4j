import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { afterEach, it, expect, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { CounterpartyPartyDirectory } from "./CounterpartyPartyDirectory"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("./LedgerSourceDialog", () => ({
  LedgerSourceDialog: ({ transactionId }: { transactionId: string }) => (
    <p>Source {transactionId}</p>
  ),
}))
afterEach(() => vi.resetAllMocks())
const caseId = "10000000-0000-4000-8000-000000000001",
  id = "10000000-0000-4000-8000-000000000002",
  partyId = "10000000-0000-4000-8000-000000000003"
const state = {
  case_id: caseId,
  revision: "a".repeat(64),
  readings: [
    {
      transaction_id: id,
      ref_id: "TX-TEST",
      account_id: id,
      currency: "GBP",
      counterparty_raw: "Printed recipient",
      description: "Source payment",
      amount_minor: "1234",
      direction: "debit",
      party: null,
      decision_transaction_id: null,
    },
  ],
  parties: [],
  history: [],
  applied: false,
  limitation: "Identity does not change money",
}
function mount() {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <CounterpartyPartyDirectory caseId={caseId} />
    </QueryClientProvider>
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Open payment identity review" })
  )
}
it("requires explicit selection and reason, then sends the captured revision", async () => {
  let current: unknown = state
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) => {
    if (options?.method === "POST")
      current = {
        ...state,
        revision: "b".repeat(64),
        applied: true,
        event_ids: [partyId],
        parties: [{ id: partyId, name: "Reviewed recipient" }],
        readings: [
          {
            ...state.readings[0],
            party: { id: partyId, name: "Reviewed recipient" },
            decision_transaction_id: id,
          },
        ],
      }
    return current
  })
  mount()
  expect(await screen.findByLabelText("Link payment TX-TEST")).not.toBeChecked()
  fireEvent.click(screen.getByLabelText("Link payment TX-TEST"))
  fireEvent.change(screen.getByLabelText("Payment party name"), {
    target: { value: "Reviewed recipient" },
  })
  expect(
    screen.getByRole("button", { name: "Save payment identity links" })
  ).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Payment identity reason"), {
    target: { value: "Checked source" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Save payment identity links" })
  )
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(expect.any(String), {
      method: "POST",
      body: {
        expected_revision: state.revision,
        transaction_ids: [id],
        reason: "Checked source",
        new_party_name: "Reviewed recipient",
      },
    })
  )
  expect(await screen.findByRole("status")).toHaveTextContent(
    "saved with decision history"
  )
  expect(screen.getByText(/Printed recipient/)).toBeInTheDocument()
})
it("opens the selected source and refuses cross-case responses", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(state)
  mount()
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Inspect identity source TX-TEST",
    })
  )
  expect(screen.getByText(`Source ${id}`)).toBeInTheDocument()
})
it("does not offer edits after a scope mismatch", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ ...state, case_id: partyId })
  mount()
  expect(await screen.findByRole("alert")).toHaveTextContent("another case")
  expect(
    screen.queryByRole("button", { name: "Save payment identity links" })
  ).not.toBeInTheDocument()
})

it("pages retained decision history without dropping its source bindings", async () => {
  const history = Array.from({ length: 26 }, (_, i) => ({
    id: `20000000-0000-4000-8000-${String(i).padStart(12, "0")}`,
    transaction_id: id,
    sequence: i + 1,
    before: { party: null, override: i > 0 },
    after: { party: null, override: true },
    reason: `History reason ${i + 1}`,
    actor: null,
    recorded_at: "2026-01-01T00:00:00Z",
  }))
  vi.mocked(fetchAPI).mockResolvedValue({ ...state, history })
  mount()
  await screen.findByLabelText("Link payment TX-TEST")
  expect(screen.getByText("History reason 1")).toBeInTheDocument()
  expect(screen.queryByText("History reason 26")).not.toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Next identity decisions",
      hidden: true,
    })
  )
  expect(screen.getByText("History reason 26")).toBeInTheDocument()
  expect(screen.queryByText("History reason 1")).not.toBeInTheDocument()
})
