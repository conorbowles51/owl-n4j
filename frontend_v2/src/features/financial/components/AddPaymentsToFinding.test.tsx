import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import type { CaseworkEntry } from "@/features/workspace/casework-api"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { useFinancialStore } from "../stores/financial.store"
import { AddPaymentsToFinding } from "./AddPaymentsToFinding"

const api = vi.hoisted(() => ({ list: vi.fn(), addFindingPayments: vi.fn() }))
vi.mock("@/features/workspace/casework-api", () => ({ caseworkAPI: api }))

const entry = (over: Partial<CaseworkEntry> = {}) =>
  ({
    id: "finding-1",
    case_id: "case",
    title: "Card payments",
    entry_type: "note",
    body: "Note",
    version: 4,
    tags: ["financial", "financial-workspace", "financial-observation"],
    links: [
      {
        id: "l",
        target_type: "evidence",
        target_id: "file",
        relationship: "context",
        source_anchor: { financial_transaction_ids: ["cited"] },
        metadata: {},
      },
    ],
    ...over,
  }) as unknown as CaseworkEntry

function mount(props: { ids: string[]; entry?: CaseworkEntry }) {
  const onClose = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AddPaymentsToFinding caseId="case" onClose={onClose} {...props} />
    </QueryClientProvider>
  )
  return onClose
}

beforeEach(() => {
  useFinancialDraftStore.setState({ drafts: {} })
  api.list.mockReset()
  api.addFindingPayments.mockReset()
})
afterEach(cleanup)

it("previews what is new, sends only the person's selection and reopens the same finding", async () => {
  api.list.mockResolvedValue({ entries: [entry()], total: 1 })
  api.addFindingPayments.mockResolvedValue({ entry: entry({ version: 5 }), added: 1, already_cited: 1 })
  const onClose = mount({ ids: ["cited", "new"] })
  fireEvent.click(await screen.findByRole("radio", { name: /Card payments/ }))
  expect(screen.getByText(/1 payment to add · 1 already cited and left as saved · 1 cited now/)).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Add 1 payment" }))
  await screen.findByText(/1 payment added; 1 already cited\. Earlier citations are unchanged\./)
  expect(api.addFindingPayments).toHaveBeenCalledWith("case", "finding-1", {
    expected_version: 4,
    transaction_ids: ["cited", "new"],
  })
  fireEvent.click(screen.getByRole("button", { name: "Open this finding" }))
  expect(useFinancialStore.getState().mainView).toBe("findings")
  expect(onClose).toHaveBeenCalled()
  const views = Object.values(useFinancialDraftStore.getState().drafts) as { expanded?: string[]; search?: string }[]
  expect(views.find((view) => view.expanded)).toMatchObject({ expanded: ["finding-1"], search: "Card payments" })
})

it("does not offer an add when every selected payment is already cited", async () => {
  mount({ ids: ["cited"], entry: entry() })
  expect(screen.getByRole("button", { name: "Add 0 payments" })).toBeDisabled()
  await waitFor(() => expect(api.addFindingPayments).not.toHaveBeenCalled())
  expect(api.list).not.toHaveBeenCalled()
})

it("says so when nothing is selected, and a refusal stays on screen", async () => {
  mount({ ids: [], entry: entry() })
  expect(screen.getByText(/No payments are selected/)).toBeVisible()
  cleanup()
  api.addFindingPayments.mockRejectedValue(Error("Entry changed from version 4 to 5"))
  mount({ ids: ["new"], entry: entry() })
  fireEvent.click(screen.getByRole("button", { name: "Add 1 payment" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("Entry changed from version 4 to 5")
})
