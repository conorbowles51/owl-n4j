import "@/styles/globals.css"
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { AddSavedStatementPayment } from "./AddSavedStatementPayment"
import { AccountConsolidation } from "./AccountConsolidation"
import { useFinancialDraftStore } from "../stores/financial-drafts"
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("./AccountOwnershipReview", () => ({
  AccountOwnershipReview: () => (
    <p>Link different accounts to their common owner</p>
  ),
}))
vi.mock("./TransactionSourceHighlight", () => ({
  TransactionSourceHighlight: () => (
    <div
      aria-label="Original PDF"
      style={{ minHeight: 520, border: "1px solid grey" }}
    >
      Synthetic source statement: Bank A, account 0001, payment 125.00
    </div>
  ),
}))
const cid = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
const aid = "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"
const bid = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
const person = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
const accounts = [aid, bid].map((id, i) => ({
  id,
  canonical_id: id,
  holder_as_recorded: "Example Company",
  institution: "Example Bank",
  identifier_as_printed: "00012345",
  currency: "MXN",
  party: null,
  holder_parties: [],
  relationships: [],
  payment_count: i + 1,
  periods: [],
}))
const directory = {
  case_id: cid,
  revision: "a".repeat(64),
  accounts,
  parties: [{ id: person, name: "Example Company" }],
  history: [],
  applied: false,
  limitation: "Synthetic review",
}
function mount(node: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      {node}
    </QueryClientProvider>
  )
}
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
  useFinancialDraftStore.setState({ drafts: {} })
})

it("keeps an amount-first draft beside the PDF, links an existing account and retries the same complete save", async () => {
  await page.viewport(1280, 850)
  const requests: unknown[] = []
  let fail = true
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/account-parties")) return directory as never
    if (options?.method === "POST") {
      requests.push(options.body)
      if (fail) throw Error("Connection interrupted")
      return { transaction_id: "saved" } as never
    }
    return {
      case_id: cid,
      source_document_id: "source",
      evidence_file_id: "file",
      revision: "a".repeat(64),
      currency: "MXN",
      pages: [1],
      details: {
        holder: "Example Company",
        institution: "Bank A",
        account_number: "0001",
      },
    } as never
  })
  const done = vi.fn()
  mount(
    <AddSavedStatementPayment caseId={cid} sourceId="source" onSaved={done} />
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Add a missed transaction" })
  )
  fireEvent.change(await screen.findByLabelText("Amount (MXN)"), {
    target: { value: "125.00" },
  })
  fireEvent.change(screen.getByLabelText("Money in or out"), {
    target: { value: "debit" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Link existing person or account" })
  )
  fireEvent.change(
    await screen.findByLabelText("Search existing counterparties"),
    { target: { value: "00012345" } }
  )
  fireEvent.click(
    (
      await screen.findAllByRole("button", {
        name: /Bank account · Example Company/,
      })
    )[1]
  )
  fireEvent.change(screen.getByLabelText("Missed payment date"), {
    target: { value: "2026-01-15" },
  })
  fireEvent.change(screen.getByLabelText("Description"), {
    target: { value: "Payment to linked account" },
  })
  const source = screen.getByLabelText("Original PDF").getBoundingClientRect()
  const editor = screen.getByLabelText("Description").getBoundingClientRect()
  expect(editor.left).toBeGreaterThan(source.right)
  fireEvent.click(screen.getByRole("button", { name: "Close and keep draft" }))
  fireEvent.click(
    screen.getByRole("button", { name: "Add a missed transaction" })
  )
  expect(await screen.findByLabelText("Amount (MXN)")).toHaveValue("125.00")
  expect(
    await screen.findByRole("button", { name: /Linked: Example Company/ })
  ).toBeVisible()
  fireEvent.change(screen.getByLabelText("Money in or out"), {
    target: { value: "credit" },
  })
  expect(screen.getByLabelText("Paid by")).toBeVisible()
  fireEvent.click(screen.getByRole("button", { name: "Save payment" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "draft is retained"
  )
  fail = false
  fireEvent.click(screen.getByRole("button", { name: "Save payment" }))
  await waitFor(() => expect(done).toHaveBeenCalledWith("saved"))
  expect(requests[0]).toEqual(requests[1])
  expect(requests[0]).toMatchObject({
    row: {
      amount_minor: "12500",
      direction: "credit",
      counterparty_link: { kind: "account", id: bid },
    },
  })
})

it("compares account records before merging and exposes a reviewed undo without removing postings", async () => {
  await page.viewport(1280, 850)
  let current = { ...directory, merges: [] as object[] }
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/preview"))
      return {
        case_id: cid,
        revision: current.revision,
        retained_id: aid,
        accounts,
        payment_count: 3,
        explanation:
          "Original statements, payments and citations remain unchanged.",
      } as never
    if (url.includes("/undo")) {
      current = {
        ...current,
        revision: "c".repeat(64),
        merges: [...current.merges, { ...current.merges[0], undone: true }],
      }
      return current as never
    }
    if (options?.method === "POST") {
      current = {
        ...current,
        revision: "b".repeat(64),
        accounts: accounts.map((a) => ({ ...a, canonical_id: aid })),
        merges: [
          {
            id: person,
            request_id: person,
            retained_id: aid,
            account_ids: [aid, bid],
            actor: "reviewer@example.test",
            reason: "Same printed account",
            recorded_at: "2026-09-23",
            undone: false,
          },
        ],
      }
      return current as never
    }
    return current as never
  })
  mount(<AccountConsolidation caseId={cid} />)
  fireEvent.click(
    screen.getByRole("button", { name: "Merge duplicate accounts" })
  )
  const choices = await screen.findAllByRole("checkbox")
  choices.forEach((choice) => fireEvent.click(choice))
  fireEvent.change(screen.getByLabelText("Retain this account for display"), {
    target: { value: aid },
  })
  fireEvent.change(screen.getByLabelText("Reason for merging or undoing"), {
    target: { value: "Same printed account" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Compare selected accounts" })
  )
  expect(
    await screen.findByLabelText("Account merge preview")
  ).toHaveTextContent("3 payments retained")
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm merge of 2 account records" })
  )
  expect(await screen.findByRole("status")).toHaveTextContent("Accounts merged")
  fireEvent.click(screen.getByText("Merge history and undo"))
  fireEvent.change(screen.getByLabelText("Reason for merging or undoing"), {
    target: { value: "Keep separate after further review" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Confirm undo of this merge" })
  )
  expect(await screen.findByRole("status")).toHaveTextContent("Merge undone")
  expect(screen.getByText("Undone")).toBeVisible()
})
