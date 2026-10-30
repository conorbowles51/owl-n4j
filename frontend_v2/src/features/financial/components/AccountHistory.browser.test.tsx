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

it("shows every holder name an account is printed under, with its statements, as a judgement call", async () => {
  await page.viewport(1280, 1000)
  useInvestigationScopeStore.getState().reset()
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (!String(url).includes("account-history")) return { items: [], total: 0 }
    return {
      case_id: "synthetic",
      applied: false,
      groups: [
        {
          key: "card:USD:liability",
          account_id: "card",
          currency: "USD",
          balance_kind: "liability",
          label: "ERICA MCCAULEY · Capital One · ****8160",
          printed_holders: [
            { name: "ERICA MCCAULEY", statements: 1, first: "2021-12-11", last: "2022-01-10" },
            { name: "ERICA HOPPER", statements: 1, first: "2022-01-11", last: "2022-02-07" },
          ],
          periods: [
            { ...period("m", "2021-12-11", "2022-01-10", "10000"), holder: "ERICA MCCAULEY" },
            { ...period("h", "2022-01-11", "2022-02-07", "10000"), holder: "ERICA HOPPER" },
          ],
        },
      ],
    }
  })
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <main className="p-4">
          <AccountHistory caseId="synthetic" />
        </main>
      </QueryClientProvider>
    )
  })
  const notice = await screen.findByTestId("printed-holders")
  expect(notice.textContent).toContain("Judgement call:")
  expect(notice.textContent).toContain(
    "ERICA MCCAULEY on 1 statement (2021-12-11 to 2022-01-10); ERICA HOPPER on 1 statement (2022-01-11 to 2022-02-07)"
  )
  expect(notice.textContent).toContain("Which person holds the account has not been established.")
  expect(screen.getByText("Printed holder: ERICA HOPPER")).toBeTruthy()
  expect(screen.getByText("Printed holder: ERICA MCCAULEY")).toBeTruthy()
})

it("keeps each printed spelling visible under the decided name and says which merged decision applies", async () => {
  await page.viewport(1280, 1000)
  useInvestigationScopeStore.getState().reset()
  vi.mocked(fetchAPI).mockImplementation(async (url) => {
    if (!String(url).includes("account-history")) return { items: [], total: 0 }
    return {
      case_id: "synthetic",
      applied: false,
      groups: [
        {
          key: "card:USD:liability",
          account_id: "card",
          currency: "USD",
          balance_kind: "liability",
          label: "ERICA MCCAULEY · Capital One · ****8160",
          printed_holders: [
            { name: "ERICA MCCAULEY", statements: 1, first: "2021-12-11", last: "2022-01-10",
              printed: [{ name: "ERICA MCCAULEY", statements: 1 }] },
            { name: "ERICA HOPPER", statements: 2, first: "2022-01-11", last: "2022-03-07",
              printed: [{ name: "ERICA HOPPER", statements: 1 }, { name: "Erica Hopper", statements: 1 }] },
          ],
          printed_holders_decision: {
            decision_id: "d2", account_id: "card", actor_name: "Claude (for Neil Byrne)", at: "2026-02-01T00:00:00Z",
            overridden: [{ decision_id: "d1", account_id: "member", actor_name: "Neil Byrne",
                           at: "2026-01-01T00:00:00Z", holders: ["ERICA MCCAULEY", "E HOPPER"] }],
          },
          periods: [
            { ...period("m", "2021-12-11", "2022-01-10", "10000"), holder: "ERICA MCCAULEY" },
            { ...period("h", "2022-01-11", "2022-02-07", "10000"), holder: "ERICA HOPPER" },
            { ...period("h2", "2022-02-08", "2022-03-07", "10000"), holder: "Erica Hopper" },
          ],
        },
      ],
    }
  })
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <main className="p-4">
          <AccountHistory caseId="synthetic" />
        </main>
      </QueryClientProvider>
    )
  })
  const notice = await screen.findByTestId("printed-holders")
  expect(notice.textContent).toContain(
    'ERICA MCCAULEY on 1 statement (2021-12-11 to 2022-01-10); ERICA HOPPER on 2 statements (2022-01-11 to 2022-03-07), printed as "ERICA HOPPER" on 1 and "Erica Hopper" on 1'
  )
  expect(screen.getByTestId("printed-holders-overridden").textContent).toBe(
    "The decision recorded 2026-02-01 by Claude (for Neil Byrne) applies. This account is merged from accounts that each carried a decision; overridden by it: the decision recorded 2026-01-01 by Neil Byrne (ERICA MCCAULEY / E HOPPER)."
  )
})
