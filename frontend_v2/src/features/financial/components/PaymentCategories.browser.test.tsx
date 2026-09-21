import "@/styles/globals.css"
import "../financial-workspace.css"
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query"
import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { LedgerRowBrowser } from "./LedgerRowBrowser"
import { paymentFixture } from "../lib/payment-fixture.test-support"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { fetchAPI } from "@/lib/api-client"
import { readSelectedPayments } from "../lib/selected-payment-source"
import type { LedgerTransaction } from "../api"

vi.mock("@/lib/api-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../lib/selected-payment-source", () => ({
  readSelectedPayments: vi.fn(),
  readSelectedPayment: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
vi.mock("../hooks/use-financial-finding-index", () => ({
  useFinancialFindingIndex: () => ({ data: [] }),
}))
vi.mock("./LedgerExportButton", () => ({ LedgerExportButton: () => null }))

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
  useFinancialDraftStore.setState({ drafts: {} })
})

it("creates reusable categories, changes an automatic category, and recategorizes every selected page with persisted results", async () => {
  await page.viewport(1440, 1050)
  let payments: LedgerTransaction[] = Array.from({ length: 30 }, (_, i) => ({
    ...paymentFixture,
    key: `p${i}`,
    description: `Payment ${i}`,
    label_version: 0,
    category: i % 2 ? "Travel" : "Shopping",
    label_sources: {
      category: { source: i % 2 ? "investigator" : "description" },
    },
  }))
  const catalog = [
    { name: "Shopping", color: "#8060a9" },
    { name: "Travel", color: "#8060a9" },
  ]
  const writes: {
    transactions: { id: string; version: number }[]
    category: string
  }[] = []
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (url === "/test-payments") return [...payments]
    if (url.includes("category-library")) {
      const caseId = new URL(url, "http://test").searchParams.get("case_id")
      if (options?.method === "POST") {
        const category = options.body as { name: string; color: string }
        catalog.push(category)
        return { case_id: caseId, category }
      }
      return { case_id: caseId, categories: [...catalog] }
    }
    if (url.includes("payment-labels") && options?.method === "PUT") {
      const body = options.body as (typeof writes)[number]
      writes.push(body)
      payments = payments.map((row) =>
        body.transactions.some((t) => t.id === row.key)
          ? {
              ...row,
              category: body.category,
              label_version: (row.label_version ?? 0) + 1,
              label_sources: { category: { source: "investigator" } },
            }
          : row
      )
      return { case_id: "category-case", updated: body.transactions.length }
    }
    throw Error(`Unexpected request: ${url}`)
  })
  vi.mocked(readSelectedPayments).mockImplementation(
    async (_caseId, ids) =>
      payments
        .filter((row) => ids.includes(row.key))
        .map((transaction) => ({ transaction })) as Awaited<
        ReturnType<typeof readSelectedPayments>
      >
  )
  function Workspace({ caseId = "category-case" }: { caseId?: string }) {
    const query = useQuery({
      queryKey: ["financial-ledger", caseId],
      queryFn: () => fetchAPI<LedgerTransaction[]>("/test-payments"),
    })
    return (
      <main className="financial-workspace bg-background p-4 text-foreground">
        <LedgerRowBrowser
          investigation
          transactions={query.data ?? []}
          exportContext={{ caseId, params: {} }}
        />
      </main>
    )
  }
  function show(caseId?: string) {
    return render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <Workspace caseId={caseId} />
      </QueryClientProvider>
    )
  }
  const view = show()
  await screen.findByText("30 of 30 imported transactions")
  await act(async () => {
    await page
      .getByRole("combobox", { name: "Rows per page" })
      .selectOptions("25")
  })
  await act(async () => {
    await page.getByRole("button", { name: "Manage categories" }).click()
  })
  await act(async () => {
    await page
      .getByRole("textbox", { name: "Category name", exact: true })
      .fill("Due diligence")
  })
  await act(async () => {
    await page.getByRole("button", { name: "Add Category" }).click()
  })
  await screen.findByText(/Category "Due diligence" saved/)
  const dialog = screen.getByRole("dialog")
  expect(
    within(dialog).getByText("Due diligence", { exact: true })
  ).toBeVisible()
  await act(async () => {
    await page
      .getByRole("button", { name: "Close", exact: true })
      .first()
      .click()
  })

  await act(async () => {
    await page
      .getByRole("button", {
        name: "Change category for Payment 0",
        exact: true,
      })
      .click()
  })
  await screen.findByLabelText("Choose category")
  expect(
    screen.getByRole("dialog", { name: "Change transaction category" })
  ).toBeVisible()
  await act(async () => {
    await page
      .getByRole("combobox", { name: "Choose category", exact: true })
      .selectOptions("Due diligence")
  })
  await act(async () => {
    await page
      .getByRole("button", { name: "Save changes", exact: true })
      .click()
  })
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  )
  expect(writes[0]).toMatchObject({
    transactions: [{ id: "p0", version: 0 }],
    category: "Due diligence",
  })
  expect(
    screen.getByRole("button", {
      name: "Change category for Payment 0",
    })
  ).toHaveTextContent("Due diligence")

  await act(async () => {
    await page
      .getByRole("button", {
        name: "Select all 30 matching payments",
        exact: true,
      })
      .click()
  })
  await act(async () => {
    await page
      .getByRole("button", { name: "Categorize selected", exact: true })
      .click()
  })
  await screen.findByLabelText("Choose category")
  expect(
    screen.getByText(/Applies to 30 selected transactions, across all pages/)
  ).toBeVisible()
  await act(async () => {
    await page
      .getByRole("combobox", { name: "Choose category", exact: true })
      .selectOptions("Due diligence")
  })
  await act(async () => {
    await page
      .getByRole("button", { name: "Save changes", exact: true })
      .click()
  })
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  )
  expect(writes[1].transactions).toHaveLength(30)
  expect(
    writes[1].transactions.find((target) => target.id === "p0")?.version
  ).toBe(1)
  expect(payments.every((row) => row.category === "Due diligence")).toBe(true)

  view.unmount()
  const reloaded = show()
  await screen.findByText("30 of 30 imported transactions")
  await act(async () => {
    await page
      .getByRole("button", { name: "Next ledger rows", exact: true })
      .click()
  })
  expect(
    screen.getByRole("button", {
      name: "Change category for Payment 29",
    })
  ).toHaveTextContent("Due diligence")
  reloaded.unmount()
  show("another-case")
  await act(async () => {
    await page.getByRole("button", { name: "Manage categories" }).click()
  })
  expect(
    await within(screen.getByRole("dialog")).findByText("Due diligence", {
      exact: true,
    })
  ).toBeVisible()
})
