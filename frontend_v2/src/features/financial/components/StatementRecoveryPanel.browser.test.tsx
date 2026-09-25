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
import { afterEach, expect, it, vi } from "vitest"
import { page, userEvent } from "vitest/browser"
import { useState } from "react"
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

for (const width of [1280, 390]) {
  it(`keeps large recovery collections scannable and retains distinct reasons, source and retry actions at ${width}px`, async () => {
    await page.viewport(width, 900)
    const newReading =
      "New reading ready to review. Confirm its account, currency and import; no earlier work was replaced."
    const overlap =
      "Several new sections overlap one saved import. Compare the account sections before adding payments."
    const section = (message: string, index: number) => ({
      statement_id: `section-${index}`,
      status: "review",
      message,
      added: 0,
    })
    let retried = false
    const retryCalls: string[] = []
    vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
      if (options?.method === "POST") {
        retryCalls.push(url)
        retried = true
        return {}
      }
      return {
        run: { id: "large-run", release: "synthetic", status: "complete" },
        total: 3,
        counts: { review: 3 },
        items: [
          {
            id: "large-first",
            file_id: "original-first",
            review_file_id: "retained-first",
            filename: "Collection A — 53 statement sections.pdf",
            status: "review",
            added: 0,
            message: "Some statement sections need review.",
            sections: [
              ...Array.from({ length: 52 }, (_, index) =>
                section(newReading, index)
              ),
              section(
                "An investigator has saved a review. Compare that work before adding payments.",
                52
              ),
            ],
          },
          {
            id: "large-second",
            file_id: "original-second",
            review_file_id: "retained-second",
            filename: "Collection B — 104 statement sections.pdf",
            status: "review",
            added: 0,
            message: retried
              ? "Retry requested. Waiting for the next recovery check."
              : "Some statement sections need review.",
            sections: Array.from({ length: 104 }, (_, index) =>
              section(overlap, index)
            ),
          },
          {
            id: "other-format",
            file_id: "source-notes",
            filename: "Financial supporting notes.docx",
            status: "review",
            added: 0,
            message: "Compare the saved source details.",
            sections: Array.from({ length: 20 }, (_, index) =>
              section(
                `Distinct review reason ${index + 1}: compare the retained source and saved account details.`,
                index
              )
            ),
          },
        ],
      }
    })
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    function Workspace() {
      const [review, setReview] = useState("")
      return (
        <main className="h-screen overflow-auto p-4">
          <div hidden={!!review}>
            <StatementRecoveryPanel
              caseId="synthetic-case"
              onReview={setReview}
            />
          </div>
          {review && (
            <section aria-label="Selected statement review">
              <h1>Statement review</h1>
              <output>{review}</output>
              <button onClick={() => setReview("")}>
                Back to recovery results
              </button>
            </section>
          )}
        </main>
      )
    }
    render(
      <QueryClientProvider client={client}>
        <Workspace />
      </QueryClientProvider>
    )
    await screen.findByRole("status")
    await act(async () => {
      await page.getByText("Review recovery results", { exact: true }).click()
    })
    const first = screen
      .getByText("Collection A — 53 statement sections.pdf")
      .closest("li")!
    const second = screen
      .getByText("Collection B — 104 statement sections.pdf")
      .closest("li")!
    expect(first).toHaveTextContent("53 sections need review · 2 reasons")
    expect(within(first).getAllByText(newReading)).toHaveLength(1)
    expect(within(first).getByText("52 sections")).toBeVisible()
    expect(first).toHaveTextContent("An investigator has saved a review.")
    expect(second).toHaveTextContent("104 sections need review · 1 reason")
    expect(within(second).getAllByText(overlap)).toHaveLength(1)
    expect(first.getBoundingClientRect().height).toBeLessThan(390)
    expect(
      within(second)
        .getByRole("button", { name: "Open statement" })
        .getBoundingClientRect().bottom
    ).toBeLessThan(900)
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width)
    await page.screenshot({
      path: `/private/tmp/loupe-recovery-grouped-${width}.png`,
      element: screen.getByRole("main"),
    })
    await act(async () => {
      await page
        .getByRole("button", { name: "Retry recovery", exact: true })
        .nth(1)
        .click()
    })
    await screen.findByText(
      "Retry requested. Waiting for the next recovery check."
    )
    expect(retryCalls).toEqual([
      "/api/financial/statement-import/deployment-recovery/items/large-second/retry?case_id=synthetic-case",
    ])
    await act(async () => {
      await page
        .getByRole("button", { name: "Open statement", exact: true })
        .nth(0)
        .click()
    })
    expect(
      screen.getByRole("region", { name: "Selected statement review" })
    ).toHaveTextContent("retained-first")
    await act(async () => {
      await page
        .getByRole("button", { name: "Back to recovery results" })
        .click()
    })
    expect(within(first).getAllByText(newReading)).toHaveLength(1)
    const other = screen
      .getByText("Financial supporting notes.docx")
      .closest("li")!
    expect(
      within(other).getByRole("link", { name: "Open source in Evidence" })
    ).toHaveAttribute(
      "href",
      "/cases/synthetic-case/evidence?file=source-notes&from=financial"
    )
    const reasons = within(other).getByRole("list", {
      name: "Section review reasons",
    })
    expect(reasons.children).toHaveLength(20)
    expect(reasons.getBoundingClientRect().height).toBeLessThanOrEqual(178)
    reasons.focus()
    await userEvent.keyboard("{End}")
    const finalReason = within(reasons).getByText(
      "Distinct review reason 20: compare the retained source and saved account details."
    )
    await waitFor(() => {
      expect(reasons.scrollTop).toBeGreaterThan(0)
      expect(finalReason.getBoundingClientRect().bottom).toBeLessThanOrEqual(
        reasons.getBoundingClientRect().bottom
      )
    })
  })
}
