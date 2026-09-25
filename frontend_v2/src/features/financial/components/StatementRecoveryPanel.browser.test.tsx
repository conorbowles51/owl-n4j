import "@/styles/globals.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { fetchAPI } from "@/lib/api-client"
import { StatementRecoveryPanel } from "./StatementRecoveryPanel"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("../hooks/use-financial-access", () => ({
  useFinancialAccess: () => ({ canEdit: true }),
}))
let client: QueryClient
afterEach(() => {
  cleanup()
  client?.clear()
  vi.resetAllMocks()
})

for (const width of [1280, 390]) {
  it(`distinguishes scheduled results from unchanged and unconfirmed sources at ${width}px`, async () => {
    await page.viewport(width, 900)
    vi.mocked(fetchAPI).mockResolvedValue({
      run: {
        id: "synthetic-run",
        release: "synthetic-followup",
        status: "complete",
      },
      total: 2,
      counts: { review: 1, kept: 1 },
      scope: {
        considered: 19,
        scheduled: 2,
        protected: 3,
        no_unresolved_work: 8,
        unconfirmed_content: 6,
      },
      items: [
        {
          id: "synthetic-item",
          file_id: "synthetic-original",
          review_file_id: "synthetic-reading",
          filename: "Synthetic retained statement.pdf",
          status: "review",
          added: 0,
          message: "The retained reading needs review before import.",
        },
      ],
    })
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const open = vi.fn()
    await act(async () => {
      render(
        <QueryClientProvider client={client}>
          <main className="p-4">
            <StatementRecoveryPanel caseId="synthetic-case" onReview={open} />
          </main>
        </QueryClientProvider>
      )
    })
    await expect
      .element(page.getByRole("status"))
      .toHaveTextContent(
        "Follow-up finished · 2 of 2 scheduled sources checked"
      )
    expect(screen.getByText(/6 sources not processed/)).toBeVisible()
    expect(screen.getByText(/3 protected sources/)).toBeVisible()
    expect(screen.getByText(/8 sources outside this pass/)).toBeVisible()
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width)
    await act(async () => {
      await page.getByText("Review recovery results", { exact: true }).click()
    })
    await expect
      .element(
        page.getByText("The retained reading needs review before import.", {
          exact: true,
        })
      )
      .toBeVisible()
    await page.screenshot({
      path: `/private/tmp/loupe-recovery-scope-${width}.png`,
    })
    await act(async () => {
      await page
        .getByRole("button", { name: "Open statement", exact: true })
        .click()
    })
    expect(open).toHaveBeenCalledWith("synthetic-reading")
    expect(
      vi
        .mocked(fetchAPI)
        .mock.calls.every(
          ([, options]) => !options?.method || options.method === "GET"
        )
    ).toBe(true)
  })
}
