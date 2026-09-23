import "@/styles/globals.css"
import { useState } from "react"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { TransactionAccountFilters } from "./TransactionAccountFilters"
import { AccountOwnershipReview } from "./AccountOwnershipReview"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { accountParties } from "../lib/account-parties"
import type { AccountSelection } from "../lib/account-selection"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, ready: true }),
}))
const caseId = "10000000-0000-4000-8000-000000000001"
const ids = [
  "10000000-0000-4000-8000-000000000002",
  "10000000-0000-4000-8000-000000000003",
]
const person = {
  id: "10000000-0000-4000-8000-000000000004",
  name: "Example business",
}
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
  useFinancialDraftStore.setState({ drafts: {} })
})
function fixture() {
  return accountParties.parse({
    case_id: caseId,
    revision: "a".repeat(64),
    parties: [],
    history: [],
    applied: false,
    limitation: "Reviewed relationships",
    accounts: ids.map((id, i) => ({
      id,
      holder_as_recorded: i ? "Example Co" : "Example Company",
      identifier_as_printed: i ? "5678" : "1234",
      institution: i ? "Bank B" : "Bank A",
      currency: i ? "EUR" : "USD",
      party: null,
    })),
  })
}
function Workspace() {
  const [selection, setSelection] = useState<AccountSelection>({})
  return (
    <main className="p-5">
      <h1>Transactions</h1>
      <TransactionAccountFilters
        caseId={caseId}
        selection={selection}
        onChange={setSelection}
      />
      <p data-testid="selection">{selection.accountHolders?.join(",")}</p>
    </main>
  )
}

it("links two accounts from Transactions, previews, saves, uses the shared holder filter and reopens at narrow width", async () => {
  let state = fixture()
  let writes = 0
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (String(url).includes("ledger-accounts"))
      return {
        case_id: caseId,
        has_more: false,
        items: state.accounts.map((a) => ({
          id: a.id,
          holder: a.holder_as_recorded,
          identifier: a.identifier_as_printed,
          institution: a.institution,
          currency: a.currency,
          party: null,
          holder_parties: a.holder_parties,
        })),
      } as never
    if (options?.method === "POST") {
      const body = options.body as {
        account_ids: string[]
        relationship: Record<string, unknown>
        reason: string
      }
      expect(body.account_ids).toEqual(ids)
      expect(body.relationship).toMatchObject({
        role: "holder",
        basis: "investigator_knowledge",
        effective_from: "2025-01-01",
        effective_to: null,
      })
      writes++
      state = accountParties.parse({
        ...state,
        revision: "b".repeat(64),
        applied: true,
        parties: [person],
        accounts: state.accounts.map((a, i) => ({
          ...a,
          holder_parties: [person],
          relationships: [
            {
              ...body.relationship,
              id: `10000000-0000-4000-8000-00000000000${i + 5}`,
              party: person,
            },
          ],
        })),
      })
    }
    return state as never
  })
  await page.viewport(1280, 900)
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const mount = () =>
    render(
      <QueryClientProvider client={client}>
        <Workspace />
      </QueryClientProvider>
    )
  mount()
  await page
    .getByRole("button", { name: "Link accounts to a person or business" })
    .click()
  fireEvent.click(
    await screen.findByRole("checkbox", { name: /Example Company · Bank A/ })
  )
  fireEvent.click(screen.getByRole("checkbox", { name: /Example Co · Bank B/ }))
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: person.name },
  })
  fireEvent.change(screen.getByLabelText("Effective from (optional)"), {
    target: { value: "2025-01-01" },
  })
  fireEvent.change(screen.getByLabelText("Reason and evidence reviewed"), {
    target: { value: "Reviewed company records and both accounts." },
  })
  // Leave with an unfinished draft; returning retains the review, without a write.
  cleanup()
  mount()
  await page
    .getByRole("button", { name: "Link accounts to a person or business" })
    .click()
  expect(await screen.findByLabelText("Name")).toHaveValue(person.name)
  expect(screen.getByLabelText("Effective from (optional)")).toHaveValue(
    "2025-01-01"
  )
  expect(writes).toBe(0)
  await page.getByRole("button", { name: "Review changes" }).click()
  expect(screen.getByLabelText("Relationship preview")).toHaveTextContent(
    "Bank B · 5678 · EUR"
  )
  await page.getByRole("button", { name: "Save reviewed relationship" }).click()
  await screen.findByText(/Relationship saved for 2 accounts/)
  await page
    .getByRole("button", { name: "Show Example business’s accounts" })
    .click()
  expect(screen.getByTestId("selection")).toHaveTextContent(
    `party:${person.id}`
  )
  expect(writes).toBe(1)
  await page.viewport(390, 844)
  await page
    .getByRole("button", { name: "Link accounts to a person or business" })
    .click()
  await waitFor(() =>
    expect(
      screen.getAllByText(/Example business · Account holder/)
    ).toHaveLength(2)
  )
  const dialog = screen.getByRole("dialog")
  expect(dialog.getBoundingClientRect().width).toBeLessThanOrEqual(390)
  expect(dialog.scrollHeight).toBeGreaterThan(dialog.clientHeight)
  await page.screenshot({ path: "/tmp/loupe-account-ownership-mobile.png" })
  await page.getByRole("button", { name: "Close", exact: true }).click()
  expect(screen.getByTestId("selection")).toHaveTextContent(
    `party:${person.id}`
  )
})

it("keeps a stale draft and requires the changed links to be reviewed before save", async () => {
  let state = fixture()
  vi.mocked(fetchAPI).mockImplementation(async () => state as never)
  const mount = () =>
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <AccountOwnershipReview caseId={caseId} accountIds={[ids[0]]} />
      </QueryClientProvider>
    )
  mount()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Link accounts to a person or business",
    })
  )
  fireEvent.change(await screen.findByLabelText("Name"), {
    target: { value: "My review" },
  })
  fireEvent.change(screen.getByLabelText("Reason and evidence reviewed"), {
    target: { value: "Reviewed source" },
  })
  cleanup()
  state = { ...state, revision: "b".repeat(64) }
  mount()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Link accounts to a person or business",
    })
  )
  const alert = await screen.findByRole("alert")
  expect(alert).toHaveTextContent("Account links changed")
  expect(screen.getByLabelText("Name")).toHaveValue("My review")
  expect(screen.getByRole("button", { name: "Review changes" })).toBeDisabled()
  fireEvent.click(
    within(alert).getByRole("button", { name: "Use reviewed current links" })
  )
  expect(screen.getByRole("button", { name: "Review changes" })).toBeEnabled()
})
