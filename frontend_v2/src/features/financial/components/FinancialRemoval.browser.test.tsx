import "@/styles/globals.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { FinancialBatchPanel } from "./FinancialBatchPanel"
import { FinancialRemovalAction } from "./FinancialRemovalAction"
vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
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

for (const fileCount of [1, 8]) {
  it(`keeps ${fileCount}-file removal scrollable and recoverable after a validation failure on a small screen`, async () => {
    await page.viewport(360, 600)
    const files = Array.from({ length: fileCount }, (_, i) => ({
      id: `00000000-0000-4000-8000-${String(i + 1).padStart(12, "0")}`,
      filename: `${i + 1} ARRENDO BBVA EUR FEB 2021 statement.pdf`,
    }))
    const proposal = {
      case_id: "case",
      revision: "a".repeat(64),
      file_count: fileCount,
      reading_count: fileCount,
      transaction_count: fileCount === 1 ? 0 : 960,
      incomplete_count: 0,
      statement_count: fileCount === 1 ? 1 : 58,
      batch_count: 2,
      archived_batch_count: 2,
      updated_batch_count: 0,
      can_remove: true,
      files,
    }
    const validation = Array.from({ length: 12 }, () => ({
      type: "uuid_parsing",
      loc: ["path", "evidence_file_id"],
      msg: "Input should be a valid UUID",
      input: "removals",
    }))
    let attempts = 0,
      previews = 0
    const confirmedRevisions: unknown[] = []
    vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
      if (url.includes("/preview"))
        return { ...proposal, revision: (previews++ ? "b" : "a").repeat(64) }
      if (url.includes("/confirm")) {
        confirmedRevisions.push(
          (options?.body as { expected_revision: string }).expected_revision
        )
        if (++attempts === 1)
          throw new ApiError(JSON.stringify(validation), 422, {
            detail: validation,
          })
        return {
          ...proposal,
          removed: true,
          restart_file_ids: files.map((f) => f.id),
        }
      }
      throw Error(`Unexpected request ${url}`)
    })
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter>
          <FinancialRemovalAction
            caseId="case"
            fileIds={files.map((f) => f.id)}
            label="Review removal"
          />
        </MemoryRouter>
      </QueryClientProvider>
    )
    await act(async () => {
      await page
        .getByRole("button", { name: "Review removal", exact: true })
        .click()
    })
    await act(async () => {
      await page
        .getByRole("button", { name: "Remove imports", exact: true })
        .click()
    })
    await expect
      .element(page.getByRole("alert"))
      .toHaveTextContent("Removal could not be confirmed. Refresh the preview")
    expect(screen.queryByText(/uuid_parsing/)).not.toBeInTheDocument()
    const dialog = screen.getByRole("dialog")
    const actions = screen.getByRole("group", { name: "Removal actions" })
    const content = screen.getByRole("region", { name: "Removal details" })
    const rect = dialog.getBoundingClientRect()
    expect(rect.top).toBeGreaterThanOrEqual(15)
    expect(rect.bottom).toBeLessThanOrEqual(window.innerHeight - 15)
    expect(rect.left).toBeGreaterThanOrEqual(15)
    expect(rect.right).toBeLessThanOrEqual(window.innerWidth - 15)
    for (const button of within(actions).getAllByRole("button")) {
      expect(button.getBoundingClientRect().bottom).toBeLessThan(
        window.innerHeight
      )
      expect(button.getBoundingClientRect().top).toBeGreaterThan(0)
    }
    expect(content.scrollHeight).toBeGreaterThan(content.clientHeight)
    content.scrollTo({ top: content.scrollHeight })
    await waitFor(() => expect(content.scrollTop).toBeGreaterThan(0))
    await page.screenshot({
      path: `/tmp/loupe-removal-${fileCount}-file-recovery.png`,
    })
    await act(async () => {
      await page
        .getByRole("button", { name: "Refresh preview", exact: true })
        .click()
    })
    await expect
      .element(
        page.getByRole("button", { name: "Remove imports", exact: true })
      )
      .toBeEnabled()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    await act(async () => {
      await page
        .getByRole("button", { name: "Remove imports", exact: true })
        .click()
    })
    await expect
      .element(page.getByRole("heading", { name: "Financial imports removed" }))
      .toBeVisible()
    expect(confirmedRevisions).toEqual(["a".repeat(64), "b".repeat(64)])
    await act(async () => {
      await page
        .getByRole("group", { name: "Removal actions" })
        .getByRole("button", { name: "Close", exact: true })
        .click()
    })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
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
