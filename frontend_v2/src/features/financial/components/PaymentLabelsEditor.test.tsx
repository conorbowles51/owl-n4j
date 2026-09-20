import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { FinancialAccessContext } from "../hooks/use-financial-access"
import { PaymentLabelsEditor } from "./PaymentLabelsEditor"
import { fetchAPI } from "@/lib/api-client"
import { readSelectedPayments } from "../lib/selected-payment-source"
import { categoryAmounts } from "../lib/category-amounts"
import { paymentFixture } from "../lib/payment-fixture.test-support"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../lib/selected-payment-source", () => ({
  readSelectedPayments: vi.fn(),
}))
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(fetchAPI).mockResolvedValue({
    case_id: "case",
    categories: ["Travel"],
  })
  vi.mocked(readSelectedPayments).mockImplementation(
    async (_caseId, ids) =>
      ids.map((id) => ({
        transaction: {
          key: id,
          label_version: 3,
          from_name: "Sender",
          to_name: "Recipient",
          category: "Travel",
        },
      })) as Awaited<ReturnType<typeof readSelectedPayments>>
  )
})
function mount(ids: string[], names = false, canEdit = true) {
  const close = vi.fn()
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <FinancialAccessContext.Provider
        value={{ canEdit, canUpload: false, ready: true, error: false }}
      >
        <PaymentLabelsEditor
          caseId="case"
          ids={ids}
          names={names}
          onClose={close}
        />
      </FinancialAccessContext.Provider>
    </QueryClientProvider>
  )
  return close
}
it("loads selections across transport pages and saves one atomic bulk category edit", async () => {
  const ids = Array.from({ length: 501 }, (_, i) => `payment-${i}`)
  const close = mount(ids)
  fireEvent.change(await screen.findByLabelText("Edit Category"), {
    target: { value: "Investigation travel" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }))
  await waitFor(() => expect(close).toHaveBeenCalled())
  expect(readSelectedPayments).toHaveBeenCalledTimes(2)
  expect(fetchAPI).toHaveBeenCalledWith(
    expect.stringContaining("/ledger/payment-labels"),
    {
      method: "PUT",
      body: {
        transactions: ids.map((id) => ({ id, version: 3 })),
        category: "Investigation travel",
      },
    }
  )
})
it("retains names and the category when a concurrent edit prevents saving", async () => {
  const close = mount(["payment"], true)
  fireEvent.change(await screen.findByLabelText("Edit To"), {
    target: { value: "Reviewed business" },
  })
  vi.mocked(fetchAPI).mockRejectedValueOnce(
    Error("Someone edited this payment. Reload.")
  )
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("Someone edited")
  expect(screen.getByLabelText("Edit To")).toHaveValue("Reviewed business")
  expect(screen.getByLabelText("Edit Category")).toHaveValue("Travel")
  expect(close).not.toHaveBeenCalled()
})
it("offers no edit action to a read-only viewer", () => {
  mount(["payment"], true, false)
  expect(
    screen.queryByRole("button", { name: "Save changes" })
  ).not.toBeInTheDocument()
})
it("confirms a suggestion without requiring an edit or reason", async () => {
  vi.mocked(readSelectedPayments).mockResolvedValue([
    {
      transaction: {
        ...paymentFixture,
        category: "Shopping",
        label_version: 0,
        label_sources: {
          category: {
            source: "description",
            explanation: "Suggested from Nike in the description.",
          },
        },
      },
    },
  ] as Awaited<ReturnType<typeof readSelectedPayments>>)
  const close = mount(["payment"])
  expect(await screen.findByLabelText("Edit Category")).toHaveFocus()
  fireEvent.click(
    await screen.findByRole("button", { name: "Confirm suggestion" })
  )
  await waitFor(() => expect(close).toHaveBeenCalled())
  expect(fetchAPI).toHaveBeenCalledWith(
    expect.stringContaining("/ledger/payment-labels"),
    {
      method: "PUT",
      body: {
        transactions: [{ id: "payment", version: 0 }],
        category: "Shopping",
      },
    }
  )
})
it("sends an explicit clear when the investigator rejects a suggestion", async () => {
  vi.mocked(readSelectedPayments).mockResolvedValue([
    {
      transaction: {
        ...paymentFixture,
        category: "Shopping",
        label_version: 0,
        label_sources: { category: { source: "description" } },
      },
    },
  ] as Awaited<ReturnType<typeof readSelectedPayments>>)
  const close = mount(["payment"])
  fireEvent.change(await screen.findByLabelText("Edit Category"), {
    target: { value: "" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }))
  await waitFor(() => expect(close).toHaveBeenCalled())
  expect(fetchAPI).toHaveBeenCalledWith(
    expect.stringContaining("/ledger/payment-labels"),
    {
      method: "PUT",
      body: { transactions: [{ id: "payment", version: 0 }], category: "" },
    }
  )
})
it("keeps category amounts exact and bank/card currencies separate", () => {
  const base = paymentFixture
  const groups = categoryAmounts([
    {
      ...base,
      category: "Travel",
      amount_minor: "9007199254740993",
      direction: "debit",
      currency: "USD",
    },
    {
      ...base,
      category: "Travel",
      amount_minor: "7",
      direction: "debit",
      currency: "USD",
    },
    {
      ...base,
      category: "Travel",
      amount_minor: "20",
      direction: "credit",
      currency: "USD",
      account_type: "credit_card",
    },
    {
      ...base,
      category: "Travel",
      amount_minor: "30",
      direction: "credit",
      currency: "EUR",
    },
  ])
  expect(groups).toHaveLength(3)
  expect(
    groups.find((group) => group.currency === "USD" && !group.card)?.debit
  ).toBe(9007199254741000n)
  expect(groups.find((group) => group.card)?.credit).toBe(20n)
})
