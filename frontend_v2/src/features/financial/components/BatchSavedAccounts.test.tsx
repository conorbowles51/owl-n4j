import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { useInvestigationScopeStore } from "../stores/investigation-scope"
import { BatchSavedAccounts } from "./BatchSavedAccounts"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
const receipt = {
  case_id: "case",
  batch_id: "batch",
  revision: "a".repeat(64),
  source_document_ids: ["source"],
  account_ids: Array.from({ length: 17 }, (_, i) => `saved-account-${i}`),
  statement_count: 20,
  transaction_count: 0,
  start_date: null,
  end_date: null,
}
const showAll = vi.fn()
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <BatchSavedAccounts
        caseId="case"
        batchId="batch"
        operationId="receipt"
        onShowAll={showAll}
      />
    </QueryClientProvider>
  )
  return client
}
beforeEach(() => {
  vi.resetAllMocks()
  useInvestigationScopeStore.getState().reset()
  useInvestigationScopeStore.getState().apply("case", {
    accountId: "unrelated-account",
    startDate: "2024-01-01",
    endDate: "2024-02-01",
  })
})
it("pages receipt accounts in bounded reads without applying or changing transaction filters", async () => {
  const historyReads: string[][] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    expect(options?.method).toBeUndefined()
    if (url.includes("/imported-transactions?"))
      return {
        ...receipt,
        account_ids: [...receipt.account_ids, receipt.account_ids[0]],
      }
    const params = new URL(url, "http://local.invalid").searchParams
    historyReads.push(params.getAll("account_ids"))
    expect(params.has("account_id")).toBe(false)
    expect(params.has("start_date")).toBe(false)
    return { case_id: "case", applied: false, groups: [] }
  })
  const before = JSON.stringify(useInvestigationScopeStore.getState().scopes)
  mount()
  await screen.findByText("1–8 of 17 accounts")
  await waitFor(() => expect(historyReads).toHaveLength(1))
  expect(historyReads[0]).toEqual(receipt.account_ids.slice(0, 8))
  fireEvent.click(screen.getByRole("button", { name: "Next saved accounts" }))
  await screen.findByText("9–16 of 17 accounts")
  await waitFor(() => expect(historyReads).toHaveLength(2))
  expect(historyReads[1]).toEqual(receipt.account_ids.slice(8, 16))
  fireEvent.click(screen.getByRole("button", { name: "Next saved accounts" }))
  await screen.findByText("17–17 of 17 accounts")
  await waitFor(() => expect(historyReads).toHaveLength(3))
  expect(historyReads[2]).toEqual(receipt.account_ids.slice(16))
  expect(
    screen.getByRole("button", { name: "Next saved accounts" })
  ).toBeDisabled()
  expect(JSON.stringify(useInvestigationScopeStore.getState().scopes)).toBe(
    before
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Show all accounts in this case" })
  )
  expect(showAll).toHaveBeenCalledOnce()
})
it("rejects a receipt for a different batch without requesting account history", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ ...receipt, batch_id: "other-batch" })
  mount()
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "another case or batch"
  )
  expect(
    vi
      .mocked(fetchAPI)
      .mock.calls.every(([url]) => url.includes("/imported-transactions?"))
  ).toBe(true)
  expect(
    screen.getByRole("button", { name: "Retry saved accounts" })
  ).toBeEnabled()
})

it("bounds a stalled receipt read and explains a retry without a save request", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) => {
    expect(options).toEqual(
      expect.objectContaining({
        timeout: 60000,
        signal: expect.any(AbortSignal),
      })
    )
    throw new DOMException("Synthetic timeout", "AbortError")
  })
  mount()
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "did not respond within one minute"
  )
  expect(
    screen.getByRole("button", { name: "Retry saved accounts" })
  ).toBeEnabled()
  expect(vi.mocked(fetchAPI).mock.calls).toHaveLength(1)
})

it("keeps the last account page in range when the current receipt becomes smaller", async () => {
  let ids = receipt.account_ids
  const reads: string[][] = []
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (url.includes("/imported-transactions?"))
      return { ...receipt, account_ids: ids }
    reads.push(
      new URL(url, "http://local.invalid").searchParams.getAll("account_ids")
    )
    return { case_id: "case", applied: false, groups: [] }
  })
  const client = mount()
  await screen.findByText("1–8 of 17 accounts")
  fireEvent.click(screen.getByRole("button", { name: "Next saved accounts" }))
  await screen.findByText("9–16 of 17 accounts")
  fireEvent.click(screen.getByRole("button", { name: "Next saved accounts" }))
  await screen.findByText("17–17 of 17 accounts")
  ids = ids.slice(0, 2)
  await act(async () => {
    await client.invalidateQueries({
      queryKey: ["financial-batch-saved-accounts"],
    })
  })
  await waitFor(() => expect(reads.at(-1)).toEqual(ids))
  expect(
    screen.queryByRole("navigation", { name: "Saved account pages" })
  ).toBeNull()
  expect(screen.getByText(/20 saved statements · 2 accounts/)).toBeVisible()
})
