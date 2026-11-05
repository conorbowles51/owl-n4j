vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
import { fireEvent, render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { GlossaryPanel } from "./GlossaryPanel"

const term = {
  id: "t1", term: "breakfast", meaning: "a cash payment", model_meaning: "a bribe", meaning_changed: true, speaker: "Sam", citations: [],
  status: "confirmed", confirmed_by: "Alex", confirmed_at: "2026-11-05T00:00:00+00:00", withdrawn_by: null, withdrawn_reason: null,
  reading_words: "A person's reading: confirmed by Alex on 2026-11-05.",
  mentions: {
    total: 2, with_rows: 1, without_rows: 1, search_limits: [], join_rule: "Within 7 days of the message.",
    items: [
      { rec: "rec://r1", kind: "message", at: "2023-03-14T09:00:00+00:00", people: ["Ana", "Sam"], rows_outside_window: 1, join_reason: null,
        rows: [{ txn: "txn://p", ref: "T-1", payment: "p", amount: "USD 500.00", date: "2023-03-15", proof_class: "p2", paid_by: "Sam", paid_to: "Ana", days_from_mention: 1 }] },
      { rec: "rec://r2", kind: "message", at: null, people: [], rows: [], rows_outside_window: 0, join_reason: "The message has no time, so no window can be set." },
    ],
  },
}

function show() {
  vi.mocked(fetchAPI).mockResolvedValue({ total: 1, confirmed: 1, items: [term], limitation: "A meaning here is a person's reading." } as never)
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><GlossaryPanel caseId="c" canEdit /></MemoryRouter>
    </QueryClientProvider>
  )
}

it("labels the term a person's reading and keeps the model's beside it", async () => {
  show()
  expect((await screen.findByTestId("glossary-reading")).textContent).toContain("A person's reading: confirmed by Alex")
  expect(screen.getByText("The model read it as: a bribe")).toBeInTheDocument()
})

it("joins each mention to its rows, or says why it joins none, and adds nothing up", async () => {
  show()
  expect((await screen.findByTestId("glossary-count")).textContent).toContain("2 mentions, 1 joined to ledger rows")
  expect(screen.getByTestId("glossary-row").textContent).toContain("USD 500.00 on 2023-03-15, Sam to Ana (1 days after)")
  expect(screen.getByText("The message has no time, so no window can be set.")).toBeInTheDocument()
  expect(screen.getByText("1 other rows between them fall outside the window.")).toBeInTheDocument()
})

it("needs a reason to withdraw", async () => {
  show()
  const button = await screen.findByRole("button", { name: "Withdraw" })
  expect(button).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Why withdraw breakfast"), { target: { value: "wrong" } })
  expect(button).not.toBeDisabled()
})
