import "@/styles/globals.css"
import { page } from "vitest/browser"
import {
  render,
  screen,
  fireEvent,
  cleanup,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { AccountIdentityReview } from "./AccountIdentityReview"
import { useFinancialDraftStore } from "../stores/financial-drafts"
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
afterEach(() => {
  cleanup()
  useFinancialDraftStore.setState({ drafts: {} })
})
const caseId = "10000000-0000-4000-8000-000000000001"
const partyId = "10000000-0000-4000-8000-000000000002"
it("records a missing account, reviews typed identifiers, retains the decision and recovers a case-graph update failure", async () => {
  await page.viewport(1100, 900)
  let state = {
    case_id: caseId,
    revision: "a".repeat(64),
    accounts: [] as unknown[],
    parties: [{ id: partyId, name: "Example business" }],
    history: [],
    identity_history: [] as unknown[],
    applied: false,
    limitation: "Ownership is separate.",
  }
  let syncAttempts = 0
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    expect(url).toContain(`case_id=${caseId}`)
    if (url.includes("/sync-graph")) {
      syncAttempts++
      if (syncAttempts === 1)
        throw Error("Case graph unavailable; saved decisions are retained.")
      return { status: "current" }
    }
    if (url.includes("/graph-status"))
      return { status: syncAttempts > 1 ? "current" : "pending" }
    if (url.includes("/graph/search"))
      return {
        nodes: [
          {
            key: "company-from-evidence",
            name: "Example business from evidence",
            type: "Company",
          },
        ],
      }
    if (url.includes("/account-parties"))
      return { ...state, accounts: [], source_choices: [] }
    if (options?.method === "POST") {
      const body = options.body as {
        account_id: string
        identifiers: { kind: string; value: string }[]
        entity_links: unknown[]
        reference: { institution: string; holder: string; currency: string }
        reason: string
      }
      expect(body.identifiers).toEqual([
        { kind: "clabe", value: "012345678901234567" },
        { kind: "customer_number", value: "998877" },
      ])
      expect(body.entity_links).toEqual([
        { party_id: partyId, entity_key: "company-from-evidence" },
      ])
      state = {
        ...state,
        applied: true,
        revision: "b".repeat(64),
        accounts: [
          {
            id: body.account_id,
            holder_as_recorded: body.reference.holder,
            institution: body.reference.institution,
            currency: body.reference.currency,
            identifier_as_printed: body.identifiers[0].value,
            party: null,
            relationships: [],
            holder_parties: [],
            referenced_only: true,
            identity_review: body,
          },
        ],
        identity_history: [
          {
            account_id: body.account_id,
            reason: body.reason,
            actor: "investigator@example.test",
            recorded_at: "2026-09-23T00:00:00Z",
          },
        ],
      }
    }
    return state
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const mount = () =>
    render(
      <QueryClientProvider client={client}>
        <AccountIdentityReview caseId={caseId} />
      </QueryClientProvider>
    )
  mount()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Review account identifiers and missing accounts",
    })
  )
  await waitFor(() =>
    expect(screen.getByLabelText("Account to identify")).toBeEnabled()
  )
  fireEvent.change(screen.getByLabelText("Account to identify"), {
    target: { value: "new" },
  })
  for (const [label, value] of [
    ["Referenced bank", "Example bank"],
    ["Suggested holder", "Example business"],
    ["Account currency", "USD"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
  fireEvent.click(screen.getByRole("button", { name: "Add identifier" }))
  fireEvent.change(screen.getByLabelText("Identifier type 1"), {
    target: { value: "clabe" },
  })
  fireEvent.change(screen.getByLabelText("Identifier value 1"), {
    target: { value: "012345678901234567" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Add identifier" }))
  fireEvent.change(screen.getByLabelText("Identifier type 2"), {
    target: { value: "customer_number" },
  })
  fireEvent.change(screen.getByLabelText("Identifier value 2"), {
    target: { value: "998877" },
  })
  fireEvent.click(
    screen.getByText(
      "Connect a reviewed person or business to another case entity"
    )
  )
  fireEvent.change(screen.getByLabelText("Reviewed identity to connect"), {
    target: { value: partyId },
  })
  fireEvent.change(screen.getByLabelText("Find existing case entity"), {
    target: { value: "Example" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Search case entities" }))
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Example business from evidence · Company",
    })
  )
  fireEvent.change(screen.getByLabelText("Reason for identity decision"), {
    target: {
      value: "Reviewed transfer instructions and separate customer identifier.",
    },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Preview identity changes" })
  )
  const preview = screen.getByLabelText("Account identity preview")
  expect(preview).toHaveTextContent("without importing any payments")
  fireEvent.click(
    within(preview).getByRole("button", { name: "Save reviewed identity" })
  )
  await screen.findByRole("status")
  fireEvent.click(screen.getByRole("button", { name: "Update case graph now" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "saved decisions are retained"
  )
  fireEvent.click(screen.getByRole("button", { name: "Update case graph now" }))
  await screen.findByText(/Up to date with the reviewed identities/)
  cleanup()
  mount()
  fireEvent.click(
    screen.getByRole("button", {
      name: "Review account identifiers and missing accounts",
    })
  )
  await screen.findByText("Record an account with no statement imported")
  expect(screen.getByLabelText("Identifier value 1")).toHaveValue(
    "012345678901234567"
  )
  expect(screen.getByLabelText("Identifier type 2")).toHaveValue(
    "customer_number"
  )
  expect(screen.getByText("Identity decision history (1)")).toBeVisible()
  await page.viewport(390, 844)
  await page.screenshot({ path: "/tmp/loupe-account-identity-mobile.png" })
  expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(390)
  client.clear()
})
