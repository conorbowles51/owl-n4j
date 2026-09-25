import "@/styles/globals.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { useAuthStore } from "@/features/auth/hooks/use-auth"
import { useStatementWorkspace } from "../stores/statement-workspace"
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
  vi.resetAllMocks()
})

for (const [filename, width] of [
  ["Synthetic statement.pdf", 1280],
  ["Synthetic source.custom", 390],
] as const) {
  it(`preserves ${filename} through guarded removal, reopening and restoration at ${width}px`, async () => {
    await page.viewport(width, 900)
    useAuthStore.setState({ user: null })
    useStatementWorkspace.setState({ selections: {}, reviewChoices: {} })
    const source = {
      id: "original",
      case_id: "case",
      original_filename: filename,
      status: "processed",
      financial_removed: false,
      financial_imports_removed: false,
      financial_visibility_revision: "initial",
      financial_visibility_changed_at: null as string | null,
      created_at: "2026-09-20T12:00:00Z",
      statement_root_evidence_id: "original",
      statement_parent_evidence_id: null as string | null,
      saved_review: {
        holder: "Investigator correction",
        rows: [{ id: "manual", amount_minor: "7500" }],
      },
    }
    const files = filename.endsWith(".pdf")
      ? [
          structuredClone(source),
          {
            ...structuredClone(source),
            id: "reading",
            statement_parent_evidence_id: "original",
            created_at: "2026-09-21T12:00:00Z",
          },
          {
            ...structuredClone(source),
            id: "previously-hidden",
            statement_parent_evidence_id: "reading",
            created_at: "2026-09-23T12:00:00Z",
            financial_removed: true,
            financial_visibility_revision: "previous-choice",
            financial_visibility_changed_at: "2026-09-23T13:00:00Z",
          },
        ]
      : [structuredClone(source)]
    // An independent upload remains independent, even with the same bytes.
    const independent = {
      ...structuredClone(source),
      id: "independent",
      original_filename: "Independent upload.pdf",
      statement_root_evidence_id: "independent",
    }
    const batchDraft = {
      state: "review",
      rows: [{ description: "Retain saved batch correction" }],
    }
    const originals = files.map((file) => structuredClone(file.saved_review))
    const originalVisibility = files.map((file) => file.financial_removed)
    const draftBefore = structuredClone(batchDraft)
    const writes: { url: string; body: unknown }[] = []
    let blocked = true
    const guard = filename.endsWith(".pdf")
      ? "This file or one of its retained readings is still processing. Wait for the reading to finish before removing it from Financial. No job was stopped."
      : "This file or one of its retained readings already has imported financial records. Use Remove imports only if you intend to withdraw those saved records."
    vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
      if (options?.method === "POST") writes.push({ url, body: options.body })
      if (url.includes("/visibility?")) {
        if (blocked) throw new ApiError(guard, 409)
        const body = options?.body as {
          removed: boolean
          expected_revision: string
        }
        const selected = files.find((file) =>
          url.includes(`/${file.id}/visibility?`)
        )!
        expect(body.expected_revision).toBe(
          selected.financial_visibility_revision
        )
        files.forEach((file) => {
          if (
            body.removed
              ? file.financial_removed
              : file.financial_visibility_revision !== body.expected_revision
          )
            return
          file.financial_removed = body.removed
          file.financial_visibility_revision = body.removed
            ? "hidden-revision"
            : "restored-revision"
          file.financial_visibility_changed_at = "2026-09-25T12:00:00Z"
        })
        return {
          case_id: "case",
          evidence_file_id: selected.id,
          financial_removed: selected.financial_removed,
          financial_visibility_revision: selected.financial_visibility_revision,
        }
      }
      if (url.startsWith("/api/evidence?"))
        return { files: [...files, independent] }
      if (url.startsWith("/api/evidence-upload-")) return []
      if (url.includes("/statement-import/files?"))
        return { case_id: "case", truncated: false, files: [] }
      if (url.includes("/deployment-recovery?"))
        return { run: null, total: 0, counts: {}, items: [] }
      throw Error(`Unexpected request: ${url}`)
    })
    const mount = () => {
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
      return () => {
        view.unmount()
        client.clear()
      }
    }
    let unmount = mount()
    await act(async () => {
      await page
        .getByRole("button", {
          name: `Remove from Financial: ${filename}`,
          exact: true,
        })
        .click()
    })
    await expect
      .element(page.getByRole("dialog"))
      .toHaveTextContent("Saved notes, corrections and batch reviews are kept")
    await act(async () => {
      await page
        .getByRole("dialog")
        .getByRole("button", { name: "Remove from Financial", exact: true })
        .click()
    })
    await expect.element(page.getByRole("alert")).toHaveTextContent(guard)
    expect(files.map((file) => file.financial_removed)).toEqual(
      originalVisibility
    )
    expect(batchDraft).toEqual(draftBefore)
    const dialog = screen.getByRole("dialog").getBoundingClientRect()
    expect(dialog.left).toBeGreaterThanOrEqual(15)
    expect(dialog.right).toBeLessThanOrEqual(width - 15)
    expect(dialog.bottom).toBeLessThanOrEqual(900 - 15)
    await page.screenshot({
      element: screen.getByRole("dialog"),
      path: `/tmp/loupe-membership-${width}-guard.png`,
    })
    await act(async () => {
      await page.getByRole("button", { name: "Keep file", exact: true }).click()
    })
    // Simulate the read finishing / a source without saved imports. The user
    // retries explicitly; the failed action never schedules destructive work.
    blocked = false
    await act(async () => {
      await page
        .getByRole("button", {
          name: `Remove from Financial: ${filename}`,
          exact: true,
        })
        .click()
    })
    await act(async () => {
      await page
        .getByRole("dialog")
        .getByRole("button", { name: "Remove from Financial", exact: true })
        .click()
    })
    await expect
      .element(page.getByRole("status"))
      .toHaveTextContent(`${filename} removed from Financial`)
    await waitFor(() => expect(screen.getByRole("status")).toHaveFocus())
    await expect
      .element(
        page.getByRole("button", {
          name: `Remove from Financial: ${filename}`,
          exact: true,
        })
      )
      .not.toBeInTheDocument()
    await expect
      .element(
        page.getByRole("button", {
          name: "Remove from Financial: Independent upload.pdf",
          exact: true,
        })
      )
      .toBeVisible()
    await act(async () => {
      await page
        .getByRole("button", { name: "View removed files", exact: true })
        .click()
    })
    await expect
      .element(
        page.getByRole("button", {
          name: `Restore to Financial: ${filename}`,
          exact: true,
        })
      )
      .toBeVisible()
    expect(
      screen.queryByRole("button", { name: "Process PDF afresh" })
    ).not.toBeInTheDocument()
    unmount()
    unmount = mount()
    await act(async () => {
      await page
        .getByRole("button", { name: "Removed files (1)", exact: true })
        .click()
    })
    await act(async () => {
      await page
        .getByRole("button", {
          name: `Restore to Financial: ${filename}`,
          exact: true,
        })
        .click()
    })
    await expect
      .element(page.getByRole("status"))
      .toHaveTextContent(
        `${filename} restored to Financial with its saved reviews`
      )
    await act(async () => {
      await page
        .getByRole("button", { name: "View financial files", exact: true })
        .click()
    })
    await expect
      .element(
        page.getByRole("button", {
          name: `Remove from Financial: ${filename}`,
          exact: true,
        })
      )
      .toBeVisible()
    expect(files.map((file) => file.saved_review)).toEqual(originals)
    expect(files.map((file) => file.financial_removed)).toEqual(
      originalVisibility
    )
    expect(files.every((file) => !file.financial_imports_removed)).toBe(true)
    expect(independent.financial_removed).toBe(false)
    expect(batchDraft).toEqual(draftBefore)
    expect(writes).toHaveLength(3)
    expect(writes.every((write) => write.url.includes("/visibility?"))).toBe(
      true
    )
    expect(
      writes.every((write) =>
        write.url.includes(
          `/${filename.endsWith(".pdf") ? "reading" : "original"}/visibility?`
        )
      )
    ).toBe(true)
    expect(writes.at(-1)?.body).toEqual({
      removed: false,
      expected_revision: "hidden-revision",
    })
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width)
    await page.screenshot({
      element: screen.getByRole("main"),
      path: `/tmp/loupe-membership-${width}-restored.png`,
    })
    unmount()
  })
}
