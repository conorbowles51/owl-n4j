import {
  render,
  screen,
  fireEvent,
  cleanup,
  within,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { InvestigatorPeople } from "./InvestigatorPeople"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { useFinancialDraftStore } from "../stores/financial-drafts"

const setup = vi.hoisted(() => ({
  rows: [] as unknown[],
  fail: false,
  unknownType: false,
}))
const party = {
  id: "00000000-0000-4000-8000-000000000010",
  name: "Example Holder",
}
const accounts = Array.from({ length: 5 }, (_, n) => ({
  id: `00000000-0000-4000-8000-00000000000${n}`,
  institution: "Example Bank",
  identifier_as_printed: `000${n}`,
  currency: n === 4 ? "USD" : "EUR",
  account_type: n === 4 ? "credit_card" : "checking",
  statement_periods: [
    {
      id: `40000000-0000-4000-8000-00000000000${n}`,
      source_document_id: `50000000-0000-4000-8000-00000000000${n}`,
      start: "2026-01-01",
      end: "2026-01-31",
    },
  ],
  holder_as_recorded: party.name,
  party: null,
  relationships: [],
  holder_parties: [party],
}))
const caseId = "10000000-0000-4000-8000-000000000001"
vi.mock("@/lib/api-client", () => ({
  fetchAPI: async () => {
    if (setup.fail) throw Error("Unavailable")
    return {
      case_id: caseId,
      revision: "a".repeat(64),
      accounts: setup.unknownType
        ? accounts.map((account, index) =>
            index === 0 ? { ...account, account_type: null } : account
          )
        : accounts,
      parties: [party],
      history: [],
      applied: false,
      limitation: "Reviewed links",
    }
  },
}))
vi.mock("../hooks/use-investigator-payments", () => ({
  useInvestigatorPayments: () => ({
    rows: setup.rows,
    params: {},
    complete: true,
    query: { isError: false, isPending: false },
  }),
}))
vi.mock("../hooks/use-financial-finding-index", () => ({
  useFinancialFindingIndex: () => ({ data: [] }),
}))
vi.mock("./InvestigationWorkspaceParts", () => ({
  WorkspaceHeading: ({ title }: { title: string }) => <h1>{title}</h1>,
  WorkspaceScope: () => null,
  InvestigationReadState: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}))
vi.mock("./AccountConsolidation", () => ({ AccountConsolidation: () => null }))
vi.mock("./AccountOwnershipReview", () => ({
  AccountOwnershipReview: () => null,
}))
vi.mock("./LedgerCounterpartiesAnalysis", () => ({
  LedgerCounterpartiesAnalysis: () => null,
}))
vi.mock("./AccountHistory", () => ({
  AccountHistory: ({ accountId }: { accountId: string }) => (
    <output aria-label="Account history">{accountId}</output>
  ),
}))
vi.mock("./LedgerRowBrowser", () => ({
  LedgerRowBrowser: ({
    transactions,
    exportContext,
  }: {
    transactions: { key: string }[]
    exportContext: unknown
  }) => (
    <section aria-label="Profile payments">
      <output>{transactions.map((r) => r.key).join(",")}</output>
      <pre>{JSON.stringify(exportContext)}</pre>
    </section>
  ),
}))
afterEach(() => {
  cleanup()
  setup.fail = false
  setup.unknownType = false
  useFinancialDraftStore.setState({ drafts: {} })
})
const renderPeople = () =>
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <InvestigatorPeople caseId={caseId} />
    </QueryClientProvider>
  )
it("keeps five owned accounts together, separates counterparty activity, and returns from a quiet account", async () => {
  setup.rows = [
    {
      ...paymentFixture,
      key: "own",
      account_id: accounts[0].id,
      account_holder_parties: [party],
    },
    {
      ...paymentFixture,
      key: "appearance",
      account_id: "outsider",
      counterparty_link: { kind: "party", id: party.id, label: party.name },
    },
  ]
  renderPeople()
  const card = await screen.findByRole("button", {
    name: /Reviewed account holder Example Holder/,
  })
  expect(
    screen.queryByRole("button", { name: /Account Example Bank/ })
  ).not.toBeInTheDocument()
  fireEvent.click(card)
  const ownAccounts = screen.getByRole("region", {
    name: "Accounts belonging to this person or business",
  })
  expect(within(ownAccounts).getAllByRole("button")).toHaveLength(5)
  expect(
    screen.getByRole("region", { name: "Profile payments" })
  ).toHaveTextContent('"scope":"owned_accounts"')
  expect(
    screen
      .getByRole("region", { name: "Profile payments" })
      .querySelector("output")
  ).toHaveTextContent(/^own$/)
  fireEvent.click(
    screen.getByRole("button", { name: "As sender or beneficiary (1)" })
  )
  expect(
    screen
      .getByRole("region", { name: "Profile payments" })
      .querySelector("output")
  ).toHaveTextContent(/^appearance$/)
  expect(
    screen.getByRole("region", { name: "Profile payments" })
  ).toHaveTextContent('"scope":"counterparty_payments"')
  expect(ownAccounts).not.toHaveTextContent("outsider")
  fireEvent.click(within(ownAccounts).getByRole("button", { name: /0004/ }))
  expect(screen.getByLabelText("Account history")).toHaveTextContent(
    accounts[4].id
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Back to person or business" })
  )
  expect(
    screen.getByRole("region", {
      name: "Accounts belonging to this person or business",
    })
  ).toBeInTheDocument()
})
it("does not show an incomplete directory as a complete set of profiles", async () => {
  setup.fail = true
  setup.rows = [paymentFixture]
  renderPeople()
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "complete account directory could not be loaded"
  )
  expect(
    screen.getByRole("button", { name: "Reload accounts" })
  ).toBeInTheDocument()
  expect(screen.queryByText(/names and accounts\./)).not.toBeInTheDocument()
})

it("shows a saved quiet account's bank, currency, source and statement dates separately from absent payments", async () => {
  setup.rows = []
  renderPeople()
  await screen.findByRole("button", {
    name: /Reviewed account holder Example Holder/,
  })
  fireEvent.change(screen.getByRole("combobox", { name: "Show" }), {
    target: { value: "account" },
  })
  const card = screen.getByRole("button", {
    name: /Account Example Bank.*0000.*Example Holder/,
  })
  expect(card).toHaveTextContent("0 matching payments")
  expect(card).toHaveTextContent("1 account · 1 bank · 1 source document")
  expect(card).toHaveTextContent("Currencies recorded: EUR")
  expect(card).toHaveTextContent(
    "Saved statement dates: 2026-01-01 to 2026-01-31 · 1 saved period"
  )
  expect(card).toHaveTextContent("Payment dates: No matching payments")
  expect(card).not.toHaveTextContent("Currencies: None")
  expect(card).not.toHaveTextContent("0 accounts")
  fireEvent.click(card)
  expect(screen.getByLabelText("Account history")).toHaveTextContent(
    accounts[0].id
  )
  expect(
    screen.getByRole("group", { name: "Saved account and statement records" })
  ).toHaveTextContent("2026-01-01 to 2026-01-31")
  fireEvent.click(
    screen.getByRole("button", { name: "Back to names and accounts" })
  )
  expect(screen.getByRole("combobox", { name: "Show" })).toHaveValue("account")
  expect(
    screen.getByRole("button", {
      name: /Account Example Bank.*0000.*Example Holder/,
    })
  ).toHaveTextContent("1 source document")
})

it("includes quiet currencies in the chooser and retains all five confirmed accounts within a filtered holder profile", async () => {
  setup.rows = []
  renderPeople()
  await screen.findByRole("button", {
    name: /Reviewed account holder Example Holder/,
  })
  expect(
    screen.getByRole("option", { name: "USD · credit cards" })
  ).toBeInTheDocument()
  fireEvent.change(
    screen.getByRole("combobox", { name: "Profile currency and account type" }),
    { target: { value: "USD:card" } }
  )
  const holder = screen.getByRole("button", {
    name: /Reviewed account holder Example Holder/,
  })
  expect(holder).toHaveTextContent("5 accounts · 1 bank · 5 source documents")
  fireEvent.click(holder)
  const accountsRegion = screen.getByRole("region", {
    name: "Accounts belonging to this person or business",
  })
  expect(within(accountsRegion).getAllByRole("button")).toHaveLength(5)
  expect(
    screen.getByRole("group", { name: "Saved account and statement records" })
  ).toHaveTextContent("not the dates of this person’s ownership or payments")
  fireEvent.click(within(accountsRegion).getByRole("button", { name: /0004/ }))
  expect(
    screen.getByRole("group", { name: "Saved account and statement records" })
  ).toHaveTextContent("Currencies recorded: USD")
  expect(
    screen.getByText(/No matching imported payments in this view/)
  ).toBeInTheDocument()
})

it("labels unresolved account references without claiming a zero bank or an inferred beneficiary currency", async () => {
  setup.rows = [
    {
      ...paymentFixture,
      key: "sender-link",
      account_id: accounts[0].id,
      counterparty_link: {
        kind: "account",
        id: "legacy-reference",
        label: "Legacy account",
      },
    },
  ]
  renderPeople()
  const card = await screen.findByRole("button", {
    name: /Account reference Legacy account/,
  })
  expect(card).toHaveTextContent(
    "1 account · Bank not recorded · Source count unavailable"
  )
  expect(card).toHaveTextContent("Currencies recorded: Not recorded")
  expect(card).toHaveTextContent("1 account number")
  expect(card).not.toHaveTextContent("Currencies recorded: EUR")
  expect(card).not.toHaveTextContent("0 accounts")
})

it("keeps an unknown-type quiet account under All and does not offer a filter unsupported by payment exports", async () => {
  setup.rows = []
  setup.unknownType = true
  renderPeople()
  await screen.findByRole("button", {
    name: /Reviewed account holder Example Holder/,
  })
  fireEvent.change(screen.getByRole("combobox", { name: "Show" }), {
    target: { value: "account" },
  })
  const card = screen.getByRole("button", {
    name: /Account Example Bank.*0000/,
  })
  expect(card).toHaveTextContent("Currencies recorded: EUR")
  expect(card).toHaveTextContent("Details not recorded: 1 account type")
  expect(
    screen.queryByRole("option", { name: /account type not recorded/ })
  ).not.toBeInTheDocument()
})
