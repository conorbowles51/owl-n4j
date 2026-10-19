import "@/styles/globals.css"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { page } from "vitest/browser"
import { fetchAPI } from "@/lib/api-client"
import { useInvestigationScopeStore } from "../stores/investigation-scope"
import { statementMonth } from "../lib/statement-month"
import type { HistoryPeriod } from "../lib/account-history"
import { AccountHistory } from "./AccountHistory"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))
let client: QueryClient
afterEach(() => {
  cleanup()
  client?.clear()
  vi.resetAllMocks()
})
const monthsOf = (year: number) =>
  Array.from(
    { length: 12 },
    (_, i) => `${year}-${String(i + 1).padStart(2, "0")}`
  )
function period(
  id: string,
  start: string,
  end: string,
  closing: string | null
): HistoryPeriod {
  return {
    id,
    source_document_id: id,
    evidence_file_id: id,
    filename: "Synthetic history.pdf",
    start,
    end,
    opening_minor: null,
    closing_minor: closing,
    status: "needs_review",
    transaction_count: 0,
    undated_count: 0,
    activity: [],
  }
}

for (const width of [1280, 390]) {
  for (const annual of [true, false]) {
    it(`keeps all ${annual ? "12 annual" : "25 multi-year"} source months readable without filling gaps or balances at ${width}px`, async () => {
      await page.viewport(width, 1000)
      useInvestigationScopeStore.getState().reset()
      const months = annual
        ? monthsOf(2026)
        : [...monthsOf(2024), ...monthsOf(2025), "2026-02"]
      const periods = annual
        ? [period("annual", "2026-01-01", "2026-12-31", null)]
        : months.map((month) => {
            const bounds = statementMonth(month)!
            return period(
              month,
              bounds.period_start,
              bounds.period_end,
              "10000"
            )
          })
      vi.mocked(fetchAPI).mockImplementation(async (url, options) => {
        expect(options?.method || "GET").toBe("GET")
        expect(url).toContain("account-history")
        return {
          case_id: "synthetic",
          applied: false,
          groups: [
            {
              key: "account:USD:asset",
              account_id: "account",
              currency: "USD",
              balance_kind: "asset",
              label: "Synthetic account",
              periods,
            },
          ],
        }
      })
      client = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      })
      await act(async () => {
        render(
          <QueryClientProvider client={client}>
            <main className="p-4">
              <AccountHistory caseId="synthetic" />
            </main>
          </QueryClientProvider>
        )
      })
      const balance = await screen.findByRole("region", {
        name: "USD bank account closing balance chart",
      })
      const activity = screen.getByRole("region", {
        name: "USD bank account activity chart",
      })
      const ticks = (chart: HTMLElement) =>
        Array.from(
          chart.querySelectorAll<SVGTextElement>(
            ".recharts-cartesian-axis-tick-value"
          )
        ).filter((tick) => /^\d{4}-\d{2}$/.test(tick.textContent || ""))
      for (const chart of [balance, activity]) {
        await waitFor(() =>
          expect(ticks(chart).map((tick) => tick.textContent)).toEqual(months)
        )
        const labels = ticks(chart)
        for (let i = 1; i < labels.length; i++) {
          expect(
            labels[i].getBoundingClientRect().left -
              labels[i - 1].getBoundingClientRect().right
          ).toBeGreaterThan(5)
        }
        expect(chart).toHaveAttribute("tabindex", "0")
        if (!annual || width === 390)
          expect(chart.scrollWidth).toBeGreaterThan(chart.clientWidth)
        chart.scrollTo({ left: chart.scrollWidth })
        await waitFor(() => {
          const last = labels.at(-1)!.getBoundingClientRect()
          const viewport = chart.getBoundingClientRect()
          expect(last.left).toBeGreaterThanOrEqual(viewport.left)
          expect(last.right).toBeLessThanOrEqual(viewport.right)
        })
      }
      expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width)
      await waitFor(
        () =>
          expect(balance.querySelectorAll(".recharts-line-dot")).toHaveLength(
            annual ? 0 : months.length
          ),
        { timeout: 5000 }
      )
      if (!annual) {
        expect(ticks(balance).map((tick) => tick.textContent)).not.toContain(
          "2026-01"
        )
        expect(
          screen.queryByRole("button", { name: "2026-01" })
        ).not.toBeInTheDocument()
      }
      await page.screenshot({
        element: balance,
        path: `/private/tmp/loupe-account-history-${annual ? "annual" : "multi-year"}-${width}.png`,
      })
    })
  }
}
