import "@/styles/globals.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { fetchAPI } from "@/lib/api-client"
import { FinancialBatchPanel } from "./FinancialBatchPanel"
vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))
vi.mock("./StatementImportPanel", () => ({ StatementImportPanel: () => null }))
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

function Location() {
  return <output aria-label="Current location">{useLocation().search}</output>
}

it("selects multiple old batches, previews removal, cancels safely, then removes and starts fresh in the same case", async () => {
  await page.viewport(1280, 1000)
  const writes: { url: string; body: unknown }[] = []
  const preview = {
    case_id: "case",
    revision: "a".repeat(64),
    file_count: 3,
    reading_count: 4,
    transaction_count: 672,
    incomplete_count: 17,
    statement_count: 53,
    batch_count: 2,
    archived_batch_count: 2,
    updated_batch_count: 0,
    can_remove: true,
    files: [
      { id: "one", filename: "Statements.pdf" },
      { id: "two", filename: "USD.pdf" },
      { id: "three", filename: "EUR.pdf" },
    ],
  }
  vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
    if (options?.method === "POST") writes.push({ url, body: options.body })
    if (url.includes("/batches/list"))
      return {
        case_id: "case",
        batches: ["old-one", "old-two"].map((id) => ({
          id,
          status: "review",
          created_at: "2026-09-20T12:00:00Z",
          file_count: 3,
        })),
      }
    if (url.includes("/removals/preview")) return preview
    if (url.includes("/removals/confirm"))
      return {
        ...preview,
        removed: true,
        restart_file_ids: ["one", "two", "three"],
      }
    if (url.includes("/batches?")) return { case_id: "case", id: "fresh-batch" }
    if (url.includes("/batches/fresh-batch"))
      return {
        id: "fresh-batch",
        case_id: "case",
        status: "preparing",
        files: [],
        counts: {},
        total: 0,
        items: [],
        ready_transactions: 0,
        ready_revision: "b".repeat(64),
      }
    throw Error(`Unexpected request ${url}`)
  })
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={["/cases/case/financial?view=statements"]}>
        <FinancialBatchPanel caseId="case" />
        <Location />
      </MemoryRouter>
    </QueryClientProvider>
  )
  await act(async () => {
    await page.getByRole("checkbox", { name: "Select batch old-one" }).click()
  })
  await act(async () => {
    await page.getByRole("checkbox", { name: "Select batch old-two" }).click()
  })
  await act(async () => {
    await page
      .getByRole("button", { name: "Remove 2 selected batches" })
      .click()
  })
  await expect.element(page.getByText(/672 transactions/)).toBeVisible()
  expect(writes.at(-1)?.body).toEqual({
    batch_ids: ["old-one", "old-two"],
    file_ids: [],
  })
  await act(async () => {
    await page.getByRole("button", { name: "Cancel", exact: true }).click()
  })
  expect(writes.some((w) => w.url.includes("/confirm"))).toBe(false)
  await act(async () => {
    await page
      .getByRole("button", { name: "Remove 2 selected batches" })
      .click()
  })
  await expect
    .element(page.getByRole("button", { name: "Remove and process afresh" }))
    .toBeEnabled()
  await act(async () => {
    await page
      .getByRole("button", { name: "Remove and process afresh" })
      .click()
  })
  await waitFor(() =>
    expect(screen.getByLabelText("Current location")).toHaveTextContent(
      "batch=fresh-batch"
    )
  )
  expect(writes.filter((w) => w.url.includes("/confirm"))).toHaveLength(1)
  expect(writes.find((w) => w.url.includes("/batches?"))?.body).toMatchObject({
    file_ids: ["one", "two", "three"],
    folder_ids: [],
  })
  await expect
    .element(
      page.getByRole("heading", { name: "Prepare statements for import" })
    )
    .toBeVisible()
})
