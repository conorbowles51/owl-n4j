import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent } from "@testing-library/react"
import { it, expect, vi, afterEach } from "vitest"
import { LedgerFilters } from "./LedgerFilters"

afterEach(() => vi.restoreAllMocks())
const answer = {
  case_id: "case-a",
  has_more: true,
  items: [
    {
      id: "account-a",
      identifier: "1234",
      holder: null,
      institution: "Bank",
      currency: "GBP",
      provisional: true,
    },
  ],
}
function mount(data = answer) {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async () => new Response(JSON.stringify(data)))
  const apply = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient()}>
      <LedgerFilters caseId="case-a" onApply={apply} />
    </QueryClientProvider>
  )
  return { fetch, apply }
}
it("keeps drafts separate, requires an explicit account choice, applies and clears", async () => {
  const { fetch, apply } = mount()
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText("Find a ledger account"), {
    target: { value: "1234" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Find accounts" }))
  fireEvent.click(await screen.findByRole("button", { name: /Select 1234/ }))
  expect(screen.getByText(/More accounts are available/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText("Ordering date from"), {
    target: { value: "2026-01-01" },
  })
  fireEvent.change(screen.getByLabelText("Ordering date through"), {
    target: { value: "2026-01-31" },
  })
  expect(apply).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole("button", { name: "Apply ledger filters" }))
  expect(apply).toHaveBeenLastCalledWith({
    accountId: "account-a",
    startDate: "2026-01-01",
    endDate: "2026-01-31",
  })
  expect(String(fetch.mock.calls[0][0])).toContain("case_id=case-a&search=1234")
  fireEvent.click(screen.getByRole("button", { name: "Clear ledger filters" }))
  expect(apply).toHaveBeenLastCalledWith({})
  expect(screen.getByLabelText("Ordering date from")).toHaveValue("")
  expect(
    screen.getByText("Selected account: All ledger accounts")
  ).toBeInTheDocument()
})
it("blocks reversed dates but permits a single day and an open bound", () => {
  const { apply } = mount()
  const start = screen.getByLabelText("Ordering date from"),
    end = screen.getByLabelText("Ordering date through")
  fireEvent.change(start, { target: { value: "2026-03-01" } })
  fireEvent.change(end, { target: { value: "2026-02-28" } })
  expect(
    screen.getByRole("button", { name: "Apply ledger filters" })
  ).toBeDisabled()
  expect(apply).not.toHaveBeenCalled()
  fireEvent.change(end, { target: { value: "2026-03-01" } })
  fireEvent.click(screen.getByRole("button", { name: "Apply ledger filters" }))
  expect(apply).toHaveBeenLastCalledWith({
    accountId: undefined,
    startDate: "2026-03-01",
    endDate: "2026-03-01",
  })
  fireEvent.change(end, { target: { value: "" } })
  fireEvent.click(screen.getByRole("button", { name: "Apply ledger filters" }))
  expect(apply).toHaveBeenLastCalledWith({
    accountId: undefined,
    startDate: "2026-03-01",
    endDate: undefined,
  })
})
it("refuses accounts returned for another case", async () => {
  mount({ ...answer, case_id: "another-case" })
  fireEvent.click(screen.getByRole("button", { name: "Find accounts" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Accounts unavailable"
  )
  expect(
    screen.queryByRole("button", { name: /Select 1234/ })
  ).not.toBeInTheDocument()
})
