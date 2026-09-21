import "@/styles/globals.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { PaymentEditsEditor } from "./PaymentEditsEditor"
import { MoneyFlowExplorer } from "./MoneyFlowExplorer"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { readSelectedPayments } from "../lib/selected-payment-source"
import { fetchAPI, ApiError } from "@/lib/api-client"
import { useFinancialDraftStore } from "../stores/financial-drafts"
const save = vi.hoisted(() =>
  vi.fn(async (payload: unknown) => {
    void payload
    return { case_id: "case", id: "saved" }
  })
)
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../lib/selected-payment-source", () => ({
  readSelectedPayments: vi.fn(),
  readSelectedPayment: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("@/features/workspace/hooks/use-casework", () => ({
  useCreateCaseworkEntry: () => ({ mutateAsync: save }),
  useUpdateCaseworkEntry: () => ({ mutateAsync: save }),
}))
const payments = [
  {
    ...paymentFixture,
    key: "one",
    amount_minor: "10000",
    currency: "USD",
    description: "Receipt",
    label_version: 0,
  },
  {
    ...paymentFixture,
    key: "two",
    amount_minor: "20000",
    currency: "USD",
    description: "Second receipt",
    label_version: 0,
  },
]
let confirms = 0
beforeEach(() => {
  confirms = 0
  save.mockClear()
  vi.mocked(readSelectedPayments).mockImplementation(
    async (_case, ids) =>
      ids.map((id) => ({
        transaction: payments.find((r) => r.key === id)!,
      })) as never
  )
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    const body = options?.body as {
      transactions: { id: string }[]
      changes: Record<string, string>
    }
    if (url.includes("payment-edits/preview"))
      return {
        case_id: "case",
        revision: "a".repeat(64),
        count: body.transactions.length,
        fields: Object.keys(body.changes),
        examples: [],
      } as never
    if (url.includes("payment-edits/confirm")) {
      confirms++
      return {
        case_id: "case",
        updated: body.transactions.length,
        replacements: body.transactions.map((r) => ({
          previous_id: r.id,
          id: r.id,
        })),
      } as never
    }
    return { case_id: "case", categories: [], entries: [], total: 0 } as never
  })
})
afterEach(() => {
  cleanup()
  useFinancialDraftStore.setState({ drafts: {} })
})
function mount(element: React.ReactNode) {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {element}
    </QueryClientProvider>
  )
}
it("reviews and saves only the enabled fields for a selected group, with a recoverable failure", async () => {
  await page.viewport(1100, 760)
  const close = vi.fn(),
    saved = vi.fn()
  mount(
    <PaymentEditsEditor
      caseId="case"
      ids={["one", "two"]}
      onClose={close}
      onSaved={saved}
    />
  )
  await screen.findByLabelText("Edit From")
  for (const [name, value] of [
    ["From", "Named sender"],
    ["Category", "Case review"],
    ["Amount", "123.45"],
  ]) {
    fireEvent.click(screen.getByLabelText(`Change ${name}`))
    fireEvent.change(screen.getByLabelText(`Edit ${name}`), {
      target: { value },
    })
  }
  fireEvent.click(screen.getByRole("button", { name: "Review changes" }))
  await screen.findByRole("region", { name: "Review transaction changes" })
  expect(confirms).toBe(0)
  const previous = vi.mocked(fetchAPI).getMockImplementation()!
  vi.mocked(fetchAPI).mockImplementationOnce(async () => {
    throw new ApiError("Someone edited this selection. Review again.", 409)
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Save changes to 2 transactions" })
  )
  await screen.findByRole("alert")
  expect(close).not.toHaveBeenCalled()
  vi.mocked(fetchAPI).mockImplementation(previous)
  fireEvent.click(screen.getByRole("button", { name: "Back to editing" }))
  expect(screen.getByLabelText("Edit From")).toHaveValue("Named sender")
  fireEvent.click(screen.getByRole("button", { name: "Review changes" }))
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Save changes to 2 transactions",
    })
  )
  await waitFor(() => expect(saved).toHaveBeenCalled())
  const request = vi
    .mocked(fetchAPI)
    .mock.calls.find(([url]) => url.includes("payment-edits/confirm"))![1]!
    .body as { changes: unknown }
  expect(request.changes).toEqual({
    from_name: "Named sender",
    category: "Case review",
    amount: "123.45",
  })
  expect(confirms).toBe(1)
})
it("single-row editing exposes current values and remains usable in a small viewport", async () => {
  await page.viewport(390, 650)
  mount(
    <PaymentEditsEditor
      caseId="case"
      ids={["one"]}
      initialField="amount"
      onClose={() => {}}
      onSaved={() => {}}
    />
  )
  expect(await screen.findByLabelText("Edit Amount")).toHaveValue("100.00")
  fireEvent.change(screen.getByLabelText("Edit Amount"), {
    target: { value: "125.50" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Review changes" }))
  await screen.findByRole("button", { name: "Save changes to 1 transaction" })
  const rect = screen.getByRole("dialog").getBoundingClientRect()
  expect(rect.height).toBeLessThan(650)
  await page.screenshot({ path: "/tmp/loupe-edit-review-mobile.png" })
})
it.each([
  ["observation", "Finding"],
  ["question", "Observation"],
] as const)(
  "uses the correct saved type and modal language for %s",
  async (kind, label) => {
    await page.viewport(1100, 760)
    mount(
      <InvestigatorFindingEditor
        caseId="case"
        initial={{ kind }}
        onClose={() => {}}
      />
    )
    expect(
      screen.getByRole("dialog", { name: `Create ${label.toLowerCase()}` })
    ).toBeVisible()
    fireEvent.change(screen.getByLabelText("Title"), {
      target: { value: `Test ${label}` },
    })
    fireEvent.change(screen.getByLabelText("Explanation"), {
      target: { value: "Recorded explanation" },
    })
    fireEvent.click(
      screen.getByRole("button", { name: `Save ${label.toLowerCase()}` })
    )
    await waitFor(() => expect(save).toHaveBeenCalled())
    expect(save.mock.calls[0][0]).toMatchObject({
      tags: expect.arrayContaining([`financial-entry-${label.toLowerCase()}`]),
    })
    await screen.findByRole("button", { name: "Open Findings & Observations" })
  }
)
it("explains a cross-currency link and follows the received funds under the chosen method", async () => {
  await page.viewport(1280, 900)
  const rows = [
    {
      ...paymentFixture,
      key: "sent",
      direction: "debit",
      currency: "USD",
      amount_minor: "10000",
      ordering_date: "2026-01-01",
      description: "FX payment",
    },
    {
      ...paymentFixture,
      key: "received",
      account_id: "yen",
      direction: "credit",
      currency: "JPY",
      amount_minor: "14500",
      ordering_date: "2026-01-02",
      description: "FX receipt",
    },
    {
      ...paymentFixture,
      key: "onward",
      account_id: "yen",
      direction: "debit",
      currency: "JPY",
      amount_minor: "7000",
      ordering_date: "2026-01-03",
      description: "Supplier",
    },
  ]
  const open = vi.fn()
  mount(
    <MoneyFlowExplorer
      caseId="case"
      rows={rows}
      overview={<p>Recorded connections</p>}
      onOpen={open}
    />
  )
  fireEvent.change(screen.getByLabelText("Money flow concept"), {
    target: { value: "fx" },
  })
  fireEvent.change(
    screen.getByLabelText("Outgoing payment before conversion"),
    { target: { value: "sent" } }
  )
  fireEvent.change(screen.getByLabelText("Receipt after conversion"), {
    target: { value: "received" },
  })
  expect(
    screen.getByText(/Implied rate: 1 USD ≈ 145.00000000 JPY/)
  ).toBeVisible()
  fireEvent.click(screen.getByRole("checkbox"))
  const results = screen.getByRole("region", { name: "Money flow results" })
  expect(
    within(results).getByText("1 onward payments under FIFO")
  ).toBeVisible()
  fireEvent.click(within(results).getByRole("button", { name: /Supplier/ }))
  expect(open).toHaveBeenCalledWith(
    ["received", "onward", "sent"],
    expect.any(String)
  )
  await page.screenshot({ path: "/tmp/loupe-cross-currency-flow.png" })
})
