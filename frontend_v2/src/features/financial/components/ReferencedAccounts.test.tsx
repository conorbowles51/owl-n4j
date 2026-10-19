import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { ReferencedAccounts } from "./ReferencedAccounts"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("./SelectedPaymentsReview", () => ({
  SelectedPaymentsReview: ({ ids }: { ids: string[] }) => (
    <p>Payments: {ids.join(", ")}</p>
  ),
}))
vi.mock("./LedgerSourceDialog", () => ({
  LedgerSourceDialog: ({ transactionId }: { transactionId: string }) => (
    <p>Source: {transactionId}</p>
  ),
}))
vi.mock("./InvestigatorFindingEditor", () => ({
  InvestigatorFindingEditor: ({
    ids,
    initial,
  }: {
    ids: string[]
    initial: { title: string; explanation: string }
  }) => (
    <div>
      <h3>{initial.title}</h3>
      <p>{initial.explanation}</p>
      <p>Attached: {ids.join(", ")}</p>
    </div>
  ),
}))
const data = {
  case_id: "case",
  revision: "a",
  offset: 0,
  limit: 25,
  total: 1,
  scanned_payments: 12,
  missing_count: 1,
  possible_match_count: 0,
  items: [
    {
      id: "reference",
      reference: "1234567890",
      kind: "account",
      partial: false,
      status: "no_statement_found",
      variants: ["account 1234567890"],
      payment_ids: ["payment-one", "payment-two"],
      payment_count: 2,
      examples: [
        {
          payment_id: "payment-one",
          text: "Payment to account 1234567890",
          start: 11,
          end: 29,
        },
      ],
      possible_accounts: [],
    },
  ],
}
function mount() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ReferencedAccounts caseId="case" onOpenTransactions={vi.fn()} />
    </QueryClientProvider>
  )
}
beforeEach(() => vi.mocked(fetchAPI).mockReset().mockResolvedValue(data))
it("opens cited payments and the PDF, then prepares a question with both payments attached", async () => {
  mount()
  fireEvent.click(
    await screen.findByRole("button", { name: "View 2 payments" })
  )
  expect(screen.getByText("Payments: payment-one, payment-two")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "View original statement" })
  )
  expect(screen.getByText("Source: payment-one")).toBeVisible()
  fireEvent.click(
    screen.getByRole("button", { name: "Save question in Findings" })
  )
  expect(
    screen.getByRole("heading", { name: "Which account is 1234567890?" })
  ).toBeVisible()
  expect(screen.getByText("Attached: payment-one, payment-two")).toBeVisible()
  expect(
    screen.getByText(
      /No matching imported statement was found.*account holder has not been established/
    )
  ).toBeVisible()
})
it("shows possible matches on request and keeps page navigation scoped to the case", async () => {
  mount()
  await screen.findByText("No matching statement imported")
  fireEvent.click(
    screen.getByRole("checkbox", {
      name: "Include references with a possible statement match",
    })
  )
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringContaining("case_id=case&offset=0&show=all"),
      expect.anything()
    )
  )
  fireEvent.change(screen.getByLabelText("Find an account reference"), {
    target: { value: "1234" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Search references" }))
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.stringContaining("search=1234"),
      expect.anything()
    )
  )
})
it("does not display references from another case", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ ...data, case_id: "another-case" })
  mount()
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "did not match this case"
  )
  expect(
    screen.queryByRole("button", { name: "Save question in Findings" })
  ).not.toBeInTheDocument()
})
