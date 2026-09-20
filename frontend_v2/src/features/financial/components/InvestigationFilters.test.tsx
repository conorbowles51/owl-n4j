import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { InvestigationFilters } from "./InvestigationFilters"
const api = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI: api }))
const account = (id: string, label: string) => ({
  id,
  display_label: label,
  identifier: id,
  holder: label,
  institution: "Example Bank",
  currency: "USD",
  provisional: false,
})
const response = (
  items = [
    account("checking", "Example checking"),
    account("savings", "Example savings"),
  ]
) => ({ case_id: "case", items, has_more: false })
beforeEach(() => {
  api.mockReset().mockResolvedValue(response())
})
function mount() {
  const apply = vi.fn()
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <InvestigationFilters
        caseId="case"
        initialParams={{ accountId: "checking", startDate: "2020-01-01" }}
        onApply={apply}
      />
    </QueryClientProvider>
  )
  return apply
}
it("retains a restored account name when searching other accounts and keeps its exact applied ID", async () => {
  const apply = mount()
  await screen.findByRole("option", { name: "Example checking USD" })
  api.mockResolvedValue(response([account("savings", "Example savings")]))
  fireEvent.change(screen.getByLabelText("Search available accounts"), {
    target: { value: "savings" },
  })
  await waitFor(() => expect(api).toHaveBeenCalledTimes(2))
  expect(
    screen.getByRole("option", { name: "Example checking USD" })
  ).toBeInTheDocument()
  expect(screen.getByLabelText("Filter account")).toHaveValue("checking")
  fireEvent.click(screen.getByRole("button", { name: "Apply" }))
  expect(apply).toHaveBeenCalledWith({
    accountId: "checking",
    startDate: "2020-01-01",
    endDate: undefined,
  })
})
it("keeps the restored choice and dates during failure and retries the same account search", async () => {
  mount()
  await screen.findByRole("option", { name: "Example checking USD" })
  api.mockRejectedValueOnce(Error("503"))
  fireEvent.change(screen.getByLabelText("Search available accounts"), {
    target: { value: "savings" },
  })
  await screen.findByRole("alert")
  expect(screen.getByLabelText("Filter account")).toHaveValue("checking")
  expect(
    screen.getByRole("option", { name: "Example checking USD" })
  ).toBeInTheDocument()
  expect(screen.getByLabelText("Transactions from")).toHaveValue("2020-01-01")
  api.mockResolvedValue(response([account("savings", "Example savings")]))
  fireEvent.click(
    screen.getByRole("button", { name: "Try loading accounts again" })
  )
  await screen.findByRole("option", { name: "Example savings USD" })
  expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  expect(api.mock.calls.at(-1)?.[0]).toContain("search=savings")
})

it("changes only dates when account selection is hidden", () => {
  const apply = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <InvestigationFilters
        caseId="case"
        accountSelection={false}
        initialParams={{ accountId: "checking", startDate: "2020-01-01" }}
        onApply={apply}
      />
    </QueryClientProvider>
  )
  expect(screen.queryByLabelText("Filter account")).not.toBeInTheDocument()
  expect(api).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Reset" }))
  expect(apply).toHaveBeenLastCalledWith({ accountId: "checking" })
  fireEvent.click(screen.getByRole("button", { name: "Apply" }))
  expect(apply).toHaveBeenLastCalledWith({
    accountId: "checking",
    startDate: undefined,
    endDate: undefined,
  })
})
