import "@/styles/globals.css"
import { useEffect, useState } from "react"
import { page } from "vitest/browser"
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, expect, it, vi } from "vitest"
import { FinancialBatchPanel } from "./FinancialBatchPanel"
import { useBatchReview } from "../lib/batch-review-context"
import { fetchAPI } from "@/lib/api-client"
import { useFinancialDraftStore } from "../stores/financial-drafts"
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("./StatementImportPanel", () => ({
  StatementImportPanel: () => {
    const context = useBatchReview()!
    const [holder, setHolder] = useState(context.draft?.holder || "")
    useEffect(() => {
      context.beforeNavigate!.current = () => context.save({ holder })
      return () => {
        context.beforeNavigate!.current = null
      }
    }, [context, holder])
    return (
      <label>
        Review holder
        <input value={holder} onChange={(e) => setHolder(e.target.value)} />
      </label>
    )
  },
}))
const batch = {
  id: "batch",
  case_id: "case",
  status: "review",
  files: [],
  counts: { ready: 1, attention: 1, imported: 1 },
  total: 0,
  items: [],
  ready_transactions: 7,
  ready_revision: "a".repeat(64),
  operations: [],
}
const item = {
  id: "first",
  file_id: "file",
  source_id: "file",
  filename: "Synthetic.pdf",
  statement_id: "statement",
  status: "attention",
  currency: "MXN",
  transaction_count: 7,
  problems: [],
  review_revision: "b".repeat(64),
}
function mount(entry = "/cases/case/financial?view=statements&batch=batch") {
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
      <MemoryRouter initialEntries={[entry]}>
        <main className="p-5">
          <FinancialBatchPanel caseId="case" />
        </main>
      </MemoryRouter>
    </QueryClientProvider>
  )
}
beforeEach(async () => {
  vi.resetAllMocks()
  useFinancialDraftStore.setState({ drafts: {} })
  await page.viewport(1280, 850)
})

it("saves before next and previous, blocks navigation on failure and explains the end of the batch", async () => {
  const drafts: Record<string, string> = {
    first: "First company",
    second: "Second company",
  }
  let fail = true
  const calls: string[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    const current = url.includes("/items/second") ? "second" : "first"
    if (options?.method === "PUT") {
      calls.push(`save:${current}`)
      if (fail) throw Error("Save interrupted. Your review is retained.")
      drafts[current] = (
        options.body as { request: { holder: string } }
      ).request.holder
      return { status: "ready", review_revision: "c".repeat(64) } as never
    }
    if (url.includes("/next-statement")) {
      calls.push(`next:${current}`)
      const previous = url.includes("direction=previous")
      return {
        case_id: "case",
        batch_id: "batch",
        item_id: previous
          ? current === "second"
            ? "first"
            : null
          : current === "first"
            ? "second"
            : null,
        position: previous ? 1 : 2,
        total: 2,
      } as never
    }
    if (url.includes("/items/"))
      return {
        ...item,
        id: current,
        review_request: {
          expected_revision: "a".repeat(64),
          holder: drafts[current],
          account_number: "0001",
          institution: "Example Bank",
          rows: [],
        },
      } as never
    return batch as never
  })
  mount("/cases/case/financial?view=statements&batch=batch&batchItem=first")
  fireEvent.change(await screen.findByLabelText("Review holder"), {
    target: { value: "Corrected company" },
  })
  await page
    .getByRole("button", { name: "Next statement", exact: true })
    .click()
  expect(await screen.findByRole("alert")).toHaveTextContent("Save interrupted")
  expect(calls).toEqual(["save:first"])
  expect(screen.getByLabelText("Review holder")).toHaveValue(
    "Corrected company"
  )
  fail = false
  await page
    .getByRole("button", { name: "Next statement", exact: true })
    .click()
  await waitFor(() =>
    expect(screen.getByLabelText("Review holder")).toHaveValue("Second company")
  )
  expect(calls.slice(-2)).toEqual(["save:first", "next:first"])
  await page
    .getByRole("button", { name: "Previous statement", exact: true })
    .click()
  await waitFor(() =>
    expect(screen.getByLabelText("Review holder")).toHaveValue(
      "Corrected company"
    )
  )
  await page
    .getByRole("button", { name: "Next statement", exact: true })
    .click()
  await waitFor(() =>
    expect(screen.getByLabelText("Review holder")).toHaveValue("Second company")
  )
  await page
    .getByRole("button", { name: "Next statement", exact: true })
    .click()
  expect(await screen.findByRole("status")).toHaveTextContent(
    "last statement (2 of 2)"
  )
})

it("checks the same import after a lost response with the browser UUID API unavailable", async () => {
  const descriptor = Object.getOwnPropertyDescriptor(
    globalThis.crypto,
    "randomUUID"
  )
  Object.defineProperty(globalThis.crypto, "randomUUID", {
    configurable: true,
    value: undefined,
  })
  let request = ""
  let submissions = 0
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url.includes("/confirm?")) {
      request = (options?.body as { request_id: string }).request_id
      submissions++
      throw Error("Connection interrupted")
    }
    if (url.includes("/operations/"))
      return {
        case_id: "case",
        batch_id: "batch",
        request_id: request,
        operation: {
          id: request,
          status: "complete",
          created_at: "2026-01-01",
          statement_count: 1,
          pending: 0,
          failed: 0,
          imported: 1,
          already_present: 0,
          transaction_count: 7,
          incomplete_count: 0,
          outcomes: [],
        },
      } as never
    return batch as never
  })
  try {
    const first = mount()
    await screen.findByRole("button", { name: "Import 7 transactions" })
    await page
      .getByRole("button", { name: "Import 7 transactions", exact: true })
      .click()
    await screen.findByText("Connection interrupted")
    expect(request).toMatch(/^[0-9a-f-]{36}$/)
    first.unmount()
    mount()
    await screen.findByRole("button", { name: "Check import result" })
    await page
      .getByRole("button", { name: "Check import result", exact: true })
      .click()
    expect(
      await screen.findByText(
        /Import complete: 1 imported.*7 transactions saved/
      )
    ).toBeVisible()
    expect(submissions).toBe(1)
  } finally {
    if (descriptor)
      Object.defineProperty(globalThis.crypto, "randomUUID", descriptor)
    else Reflect.deleteProperty(globalThis.crypto, "randomUUID")
  }
})

it("keeps unresolved batches active and shows completed batches only in retained history", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({
    case_id: "case",
    batches: [
      {
        id: "active",
        status: "review",
        created_at: "2026-09-23",
        file_count: 3,
        completed: false,
        filenames: ["Needs review.pdf"],
      },
      {
        id: "finished",
        status: "complete",
        created_at: "2026-09-22",
        file_count: 2,
        completed: true,
        filenames: ["Saved.pdf"],
      },
    ],
  } as never)
  mount("/cases/case/financial?view=statements")
  expect(await screen.findByText(/Needs review.pdf/)).toBeVisible()
  expect(screen.queryByText(/Saved.pdf/)).toBeNull()
  await page
    .getByRole("checkbox", { name: "Show completed batches (history)" })
    .click()
  expect(await screen.findByText(/Saved.pdf/)).toBeVisible()
  expect(screen.getByText("Completed · retained in history")).toBeVisible()
  cleanup()
})
