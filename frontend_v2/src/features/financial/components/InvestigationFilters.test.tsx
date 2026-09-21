import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, within } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { InvestigationFilters } from "./InvestigationFilters"
const api = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI: api }))
const account = (id: string, holder: string) => ({
  id,
  display_label: id,
  identifier: id,
  holder,
  institution: "Example Bank",
  currency: "USD",
  provisional: false,
})
const response = () => ({
  case_id: "case",
  items: [
    account("checking", "Example Company"),
    account("savings", "Example Company"),
    account("other", "Other Company"),
  ],
  has_more: false,
})
beforeEach(() => {
  api.mockReset().mockResolvedValue(response())
})
function mount(accountSelection = true) {
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
        accountSelection={accountSelection}
        onApply={apply}
      />
    </QueryClientProvider>
  )
  return apply
}
it("selects multiple people and accounts, retains selection during search and applies the exact scope", async () => {
  const apply = mount()
  fireEvent.click(
    screen.getByLabelText("Bank account filter").querySelector("summary")!
  )
  const savings = await screen.findByRole("checkbox", { name: "savings · USD" })
  fireEvent.click(savings)
  fireEvent.change(screen.getByLabelText("Search bank account"), {
    target: { value: "savings" },
  })
  expect(savings).toBeChecked()
  expect(
    screen.getByRole("button", {
      name: "Remove checking · USD from bank account filter",
    })
  ).toBeInTheDocument()
  fireEvent.click(
    screen.getByLabelText("Person or company filter").querySelector("summary")!
  )
  fireEvent.click(screen.getByRole("checkbox", { name: "Example Company" }))
  fireEvent.click(screen.getByRole("checkbox", { name: "Other Company" }))
  fireEvent.click(screen.getByRole("button", { name: "Apply" }))
  expect(apply).toHaveBeenLastCalledWith({
    accountId: undefined,
    accountIds: ["checking", "savings"],
    accountHolders: ["example company", "other company"],
    startDate: "2020-01-01",
    endDate: undefined,
  })
})
it("keeps restored selections and dates during failure, then reloads the directory", async () => {
  api.mockRejectedValueOnce(Error("503"))
  const apply = mount()
  const error = await screen.findByRole("alert")
  expect(screen.getByLabelText("Transactions from")).toHaveValue("2020-01-01")
  fireEvent.click(within(error).getByRole("button", { name: "Try again" }))
  fireEvent.click(
    screen.getByLabelText("Bank account filter").querySelector("summary")!
  )
  expect(
    await screen.findByRole("checkbox", { name: "checking · USD" })
  ).toBeChecked()
  fireEvent.click(screen.getByRole("button", { name: "Apply" }))
  expect(apply).toHaveBeenLastCalledWith(
    expect.objectContaining({ accountId: "checking", startDate: "2020-01-01" })
  )
})
it("changes only dates when account selection is hidden", () => {
  const apply = mount(false)
  expect(screen.queryByLabelText("Bank account filter")).not.toBeInTheDocument()
  expect(api).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Reset" }))
  expect(apply).toHaveBeenLastCalledWith(
    expect.objectContaining({ accountId: "checking" })
  )
  fireEvent.click(screen.getByRole("button", { name: "Apply" }))
  expect(apply).toHaveBeenLastCalledWith(
    expect.objectContaining({
      accountId: "checking",
      startDate: undefined,
      endDate: undefined,
    })
  )
})
