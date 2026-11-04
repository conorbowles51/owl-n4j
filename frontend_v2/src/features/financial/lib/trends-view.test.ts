/**
 * The Trends page's figures from the server equal the browser's own calculation over the same payments.
 *
 * `trends-parity.fixture.json` holds payments made to reach every rule (first seen, weekly and monthly schedules,
 * larger payments, returned transfers by bank reference and by "Ref:" in the description, unnamed payments with
 * and without a stated reason, linked counterparties, suggested names and categories, undated, statement-end-only
 * and impossible dates, unreadable and negative amounts, a card and a second currency) and the server's answers
 * for several choices of group and periods. The backend test (test_financial_trends_first_view.py) checks the
 * server still gives those answers; this one checks the browser's functions give the same figures. The equality
 * over the six live cases is a gate run outside the suite.
 */
import { describe, expect, it } from "vitest"
import type { LedgerTransaction } from "../api"
import fixture from "./trends-parity.fixture.json"
import {
  changeDrivers,
  defaultTrendRanges,
  investigateTrends,
  rangeError,
  sortGroups,
  type CoverageInput,
} from "./investigation-trends"
import { paymentDay, paymentGroup } from "./investigator-workspace"
import { matchesCategories } from "../hooks/use-payment-categories"
import {
  driversFromServer,
  serverGroups,
  trendsFromServer,
  type TrendsServerView,
} from "./trends-view"

const rows = fixture.rows as unknown as LedgerTransaction[]
const keys = (list: { key: string }[]) => list.map((r) => r.key)
const coverages: CoverageInput[] = [
  { available: false, truncated: false, periods: [] },
  {
    available: true,
    truncated: false,
    periods: [
      { account_id: "account", account_label: "", start: "2020-12-01", end: "2021-02-28", source_status: "admitted" },
      { account_id: "card-main", account_label: "", start: "2021-01-01", end: "2021-01-31", source_status: "admitted", incomplete: true },
    ],
  },
]

describe("Trends from the server", () => {
  for (const { ask, server } of fixture.scenarios as unknown as {
    ask: {
      group?: string
      categories?: string[]
      earlier?: { start: string; end: string }
      later?: { start: string; end: string }
    }
    server: TrendsServerView
  }[]) {
    it(`equals the browser's calculation for ${JSON.stringify(ask)}`, () => {
      const view = { ...server, available: true, case_id: fixture.case_id }
      const own = rows.filter((r) => matchesCategories(r, ask.categories ?? []))
      const counts = new Map<string, number>()
      for (const r of own) counts.set(paymentGroup(r), (counts.get(paymentGroup(r)) || 0) + 1)
      const groups = sortGroups(counts)
      const group = ask.group && groups.includes(ask.group) ? ask.group : groups[0]
      const scoped = own.filter((r) => paymentGroup(r) === group)
      const defaults = defaultTrendRanges(scoped)
      const earlier = ask.earlier ?? defaults.earlier,
        later = ask.later ?? defaults.later
      expect(serverGroups(view)).toEqual(groups)
      expect(view.group).toBe(group)
      expect([view.earlier, view.later]).toEqual([earlier, later])
      expect([view.scoped_count, view.scoped_dated]).toEqual([scoped.length, scoped.some((r) => !!paymentDay(r))])
      expect(view.error).toBe(rangeError(earlier, later))
      if (view.error) {
        expect(view.result).toBeNull()
        return
      }
      for (const coverage of coverages) {
        const browser = investigateTrends(scoped, group, earlier, later, coverage)
        const fromServer = trendsFromServer(view, coverage)!
        expect(fromServer.accounts).toEqual(browser.accounts)
        expect(fromServer.coverage).toEqual(browser.coverage)
        expect(fromServer.comparable).toBe(browser.comparable)
        expect(fromServer.totals).toEqual(browser.totals)
        expect(keys(fromServer.unknownDates)).toEqual(keys(browser.unknownDates))
        expect(fromServer.invalidAmountCount).toBe(browser.invalidAmounts.length)
        expect(fromServer.historyCount).toBe(browser.historyCount)
        expect(
          fromServer.observations.map((o) => ({ ...o, rows: keys(o.rows), earlierRows: keys(o.earlierRows) }))
        ).toEqual(
          browser.observations.map((o) => ({ ...o, rows: keys(o.rows), earlierRows: keys(o.earlierRows) }))
        )
        for (const direction of ["debit", "credit"])
          for (const by of ["name", "category"] as const)
            expect(
              driversFromServer(view, direction, by).map((d) => ({ ...d, earlier: keys(d.earlier), later: keys(d.later) }))
            ).toEqual(
              changeDrivers(browser.before, browser.after, direction, by).map((d) => ({
                ...d,
                earlier: keys(d.earlier),
                later: keys(d.later),
              }))
            )
      }
    })
  }
  it("covers every kind of observation", () => {
    const kinds = new Set(
      (fixture.scenarios as unknown as { server: TrendsServerView }[]).flatMap(
        (s) => s.server.result?.observations.map((o) => o.kind) ?? []
      )
    )
    expect([...kinds].sort()).toEqual(["first-seen", "larger", "recurring", "return"])
  })
})
