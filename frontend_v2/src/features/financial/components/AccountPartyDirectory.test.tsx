// This existing workflow fixture has case editing and upload access.
vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({
    canEdit: true,
    canUpload: true,
    ready: true,
    error: false,
  }),
}))
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { fetchAPI } from "@/lib/api-client"
import { AccountPartyDirectory } from "./AccountPartyDirectory"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
afterEach(() => vi.resetAllMocks())
beforeEach(() => useFinancialDraftStore.setState({ drafts: {} }))
const caseId = "10000000-0000-4000-8000-000000000001",
  accountId = "10000000-0000-4000-8000-000000000002",
  partyId = "10000000-0000-4000-8000-000000000003"
const party = { id: partyId, name: "Reviewed person" }
const state = {
  case_id: caseId,
  revision: "a".repeat(64),
  accounts: [
    {
      id: accountId,
      holder_as_recorded: "Printed name",
      identifier_as_printed: "1234",
      institution: null,
      currency: "GBP",
      party,
    },
  ],
  parties: [party],
  history: [],
  applied: false,
  limitation: "Conditional",
}
function mount() {
  const onChoose = vi.fn()
  const view = render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <AccountPartyDirectory caseId={caseId} onChoose={onChoose} />
    </QueryClientProvider>
  )
  return Object.assign(onChoose, { unmount: view.unmount })
}
it("uses saved account IDs and captures the actual decision revision", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(state)
  const choose = mount()
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Use Reviewed person in this perspective",
    })
  )
  expect(choose).toHaveBeenCalledWith([accountId], state)
  expect(screen.getByText(/Printed name/)).toBeInTheDocument()
})
it("requires a reason and sends an explicit stale-review revision", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) =>
    options?.method === "POST"
      ? {
          ...state,
          applied: true,
          accounts: [
            {
              ...state.accounts[0],
              party: { ...party, name: "Different person" },
            },
          ],
        }
      : state
  )
  mount()
  fireEvent.click(await screen.findByLabelText(`Select account ${accountId}`))
  fireEvent.change(screen.getByLabelText("New account party name"), {
    target: { value: "Different person" },
  })
  expect(
    screen.getByRole("button", { name: "Save account links" })
  ).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Account party link reason"), {
    target: { value: "Reviewed source" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Save account links" }))
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(expect.any(String), {
      method: "POST",
      body: {
        expected_revision: state.revision,
        account_ids: [accountId],
        new_party_name: "Different person",
        reason: "Reviewed source",
      },
    })
  )
})
it("refuses a directory returned for another case", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ ...state, case_id: partyId })
  mount()
  expect(await screen.findByRole("alert")).toHaveTextContent("another case")
  expect(screen.queryByText("Save account links")).not.toBeInTheDocument()
})

it("keeps an account-link draft and requires the latest revision to be reviewed after reopening", async () => {
  vi.mocked(fetchAPI).mockResolvedValue(state)
  const first = mount()
  fireEvent.click(await screen.findByLabelText(`Select account ${accountId}`))
  fireEvent.change(screen.getByLabelText("New account party name"), {
    target: { value: "New holder" },
  })
  fireEvent.change(screen.getByLabelText("Account party link reason"), {
    target: { value: "Checked both statements" },
  })
  first.unmount()
  vi.mocked(fetchAPI).mockResolvedValue({ ...state, revision: "b".repeat(64) })
  mount()
  expect(
    await screen.findByLabelText(`Select account ${accountId}`)
  ).toBeChecked()
  expect(screen.getByLabelText("New account party name")).toHaveValue(
    "New holder"
  )
  expect(screen.getByLabelText("Account party link reason")).toHaveValue(
    "Checked both statements"
  )
  expect(
    screen.getByRole("button", { name: "Save account links" })
  ).toBeDisabled()
  fireEvent.click(
    screen.getByRole("button", { name: "Use latest account records" })
  )
  fireEvent.click(screen.getByRole("button", { name: "Save account links" }))
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({
          expected_revision: "b".repeat(64),
          account_ids: [accountId],
          reason: "Checked both statements",
        }),
      })
    )
  )
  expect(await screen.findByRole("alert")).toHaveTextContent("not confirmed")
  expect(screen.getByLabelText("Account party link reason")).toHaveValue(
    "Checked both statements"
  )
})

it("does not announce success when the returned account links do not match the requested person", async () => {
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) =>
    options?.method === "POST" ? { ...state, applied: true } : state
  )
  mount()
  fireEvent.click(await screen.findByLabelText(`Select account ${accountId}`))
  fireEvent.change(screen.getByLabelText("New account party name"), {
    target: { value: "Different holder" },
  })
  fireEvent.change(screen.getByLabelText("Account party link reason"), {
    target: { value: "Review explanation" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Save account links" }))
  expect(await screen.findByRole("alert")).toHaveTextContent("not confirmed")
  expect(screen.queryByRole("status")).not.toBeInTheDocument()
  expect(screen.getByLabelText("Account party link reason")).toHaveValue(
    "Review explanation"
  )
})
