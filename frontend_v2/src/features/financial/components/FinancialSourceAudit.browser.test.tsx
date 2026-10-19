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
import { MemoryRouter } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useStatementWorkspace } from "../stores/statement-workspace"
import {
  auditDetail,
  auditGroup,
  auditList,
} from "../test/source-audit-fixtures"
import { StatementFilesPanel } from "./StatementFilesPanel"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true, canUpload: true }),
}))
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.resetAllMocks()
})

for (const width of [1280, 390]) {
  it(`inspects retained content and finds the exact source controls with a return path at ${width}px`, async () => {
    await page.viewport(width, 900)
    useAuthStore.setState({ user: null })
    useStatementWorkspace.setState({ selections: {}, reviewChoices: {} })
    const groups = [auditGroup(0), auditGroup(1), auditGroup(2)]
    const files = groups.map((group) => ({
      id: group.current_file_id,
      case_id: "case",
      original_filename: group.filename,
      status: "processed",
      statement_root_evidence_id: group.root_file_id,
      financial_removed: group.visibility === "hidden",
    }))
    const reads: string[] = []
    vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
      expect(options?.method || "GET").toBe("GET")
      reads.push(url)
      const parsed = new URL(url, "http://localhost")
      if (parsed.pathname === "/api/financial/source-audit")
        return auditList(
          groups,
          parsed.searchParams.get("visibility") || "visible",
          Number(parsed.searchParams.get("offset"))
        )
      if (parsed.pathname.startsWith("/api/financial/source-audit/")) {
        const id = parsed.pathname.split("/").at(-1)!
        const group = groups.find(
          (group) => group.current_file_id === id || group.root_file_id === id
        )!
        return auditDetail(
          group,
          id,
          Number(parsed.searchParams.get("text_offset"))
        )
      }
      if (url.startsWith("/api/evidence?")) return { files }
      if (url.startsWith("/api/evidence-upload-")) return []
      if (url.includes("/statement-import/files?"))
        return { case_id: "case", files: [], truncated: false }
      if (url.includes("/deployment-recovery?"))
        return { run: null, total: 0, counts: {}, items: [] }
      throw Error(`Unexpected request: ${url}`)
    })
    const nativeFetch = window.fetch.bind(window)
    vi.spyOn(window, "fetch").mockImplementation((input, options) => {
      if (String(input) === "/api/evidence/reading-1/file") {
        expect(options?.method || "GET").toBe("GET")
        return Promise.resolve(
          new Response(
            "Synthetic original source contents — no source changed."
          )
        )
      }
      if (String(input).includes("/api/"))
        throw Error(`Unexpected native request ${String(input)}`)
      return nativeFetch(input, options)
    })
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const view = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <main className="p-4">
            <StatementFilesPanel caseId="case" register />
          </main>
        </MemoryRouter>
      </QueryClientProvider>
    )
    await expect
      .element(
        page.getByRole("heading", { name: "2 matching files", exact: true })
      )
      .toBeVisible()
    expect(reads.some((url) => url.includes("source-audit"))).toBe(false)
    await act(async () => {
      await page
        .getByRole("button", { name: "Review Financial sources", exact: true })
        .click()
    })
    await expect
      .element(
        page.getByRole("heading", { name: "Sources 1–2 of 2", exact: true })
      )
      .toBeVisible()
    await act(async () => {
      await page
        .getByRole("list", { name: "Financial sources for inspection" })
        .getByRole("button", { name: "Inspect source", exact: true })
        .nth(1)
        .click()
    })
    await expect
      .element(
        page.getByText(
          "Saved financial records or their history are retained.",
          { exact: true }
        )
      )
      .toBeVisible()
    await expect
      .element(page.getByText(/Synthetic retained text/))
      .toBeVisible()
    await act(async () => {
      await page
        .getByRole("button", { name: "Open original", exact: true })
        .click()
    })
    await expect
      .element(page.getByRole("dialog"))
      .toHaveTextContent(
        "Synthetic original source contents — no source changed."
      )
    await act(async () => {
      await page
        .getByRole("button", { name: "Close document", exact: true })
        .click()
    })
    await act(async () => {
      await page.getByRole("button", { name: "Next text", exact: true }).click()
    })
    await expect
      .element(page.getByText(/characters 4001–6000 of 6000/))
      .toBeVisible()
    await act(async () => {
      await page
        .getByLabelText("Source reading", { exact: true })
        .selectOptions("source-1")
    })
    await expect
      .element(page.getByText(/No stored text is available/))
      .toHaveTextContent("financial relevance is unknown")
    await page.screenshot({
      element: screen.getByRole("region", { name: "Review Financial sources" }),
      path: `/tmp/loupe-source-audit-${width}-inspect.png`,
    })
    await act(async () => {
      await page
        .getByRole("list", { name: "Financial sources for inspection" })
        .getByRole("button", { name: "Find in files", exact: true })
        .nth(1)
        .click()
    })
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: "1 matching files" })
      ).toHaveFocus()
    )
    const selected = screen.getByRole("article", {
      name: "Financial source Shared name.txt",
    })
    expect(
      within(selected).getByRole("link", { name: "Open source in Evidence" })
    ).toHaveAttribute(
      "href",
      "/cases/case/evidence?file=reading-1&from=financial"
    )
    await act(async () => {
      await page
        .getByRole("button", { name: "Back to source review", exact: true })
        .click()
    })
    expect(
      screen.getByRole("region", { name: "Review Financial sources" })
        .parentElement
    ).toHaveFocus()
    await expect
      .element(page.getByLabelText("Source reading", { exact: true }))
      .toHaveValue("source-1")
    await act(async () => {
      await page
        .getByLabelText("Sources to review", { exact: true })
        .selectOptions("hidden")
    })
    await expect
      .element(
        page.getByRole("heading", { name: "Sources 1–1 of 1", exact: true })
      )
      .toBeVisible()
    await act(async () => {
      await page
        .getByRole("list", { name: "Financial sources for inspection" })
        .getByRole("button", { name: "Find in files", exact: true })
        .click()
    })
    await waitFor(() =>
      expect(
        screen.getByRole("heading", {
          name: "Removed files · 1 matching files",
        })
      ).toHaveFocus()
    )
    await expect
      .element(
        page.getByRole("button", {
          name: "Restore to Financial: Synthetic source 2.custom",
          exact: true,
        })
      )
      .toBeVisible()
    expect(files[2].financial_removed).toBe(true)
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width)
    await page.screenshot({
      element: screen.getByRole("main"),
      path: `/tmp/loupe-source-audit-${width}-found.png`,
    })
    view.unmount()
    client.clear()
  })
}
