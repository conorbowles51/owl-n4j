import { describe, expect, it } from "vitest"
import { paymentFixture } from "./payment-fixture.test-support"
import type { LedgerTransaction } from "../api"
import {
  changeDrivers,
  changePercent,
  coverageFor,
  defaultTrendRanges,
  investigateTrends,
  monthRange,
  rangeError,
  trendObservations,
  type CoverageInput,
} from "./investigation-trends"
const row = (
  key: string,
  date: string,
  amount = "100",
  name = "Vendor",
  extra: Partial<LedgerTransaction> = {}
): LedgerTransaction => ({
  ...paymentFixture,
  key,
  ordering_date: date,
  transaction_date: date,
  currency: "USD",
  direction: "debit",
  from_name: "Owner",
  to_name: name,
  amount_minor: amount,
  description: `Payment ${key}`,
  account_label: "Owner account",
  ...extra,
})
const earlier = monthRange("2021-01"),
  later = monthRange("2021-02")
const covered: CoverageInput = {
  available: true,
  truncated: false,
  periods: [
    {
      account_id: "account",
      account_label: "Owner",
      start: "2021-01-01",
      end: "2021-02-28",
      source_status: "admitted",
    },
  ],
}
describe("investigative trends", () => {
  it("uses calendar periods and rejects invalid, reversed and overlapping dates", () => {
    expect(monthRange("2024-02").end).toBe("2024-02-29")
    expect(monthRange("2021-13")).toEqual({ start: "", end: "" })
    expect(defaultTrendRanges([row("a", "2021-02-12")])).toEqual({
      earlier,
      later,
    })
    expect(rangeError(earlier, later)).toBeNull()
    expect(rangeError(later, earlier)).toMatch(/before/)
    expect(
      rangeError({ start: "2021-02-29", end: "2021-03-01" }, later)
    ).toMatch(/valid/)
    expect(rangeError(earlier, earlier)).toMatch(/overlap/)
  })
  it("merges adjacent and overlapping statements but flags gaps, other accounts, incomplete and truncated inputs", () => {
    const input = {
      ...covered,
      periods: [
        { ...covered.periods[0], end: "2021-01-15" },
        { ...covered.periods[0], start: "2021-01-16", end: "2021-01-31" },
      ],
    }
    const accounts = [{ id: "account", label: "Owner" }]
    expect(coverageFor(earlier, accounts, input)).toMatchObject({
      full: true,
      details: [{ coveredDays: 31, totalDays: 31 }],
    })
    input.periods[1].start = "2021-01-17"
    expect(coverageFor(earlier, accounts, input)).toMatchObject({
      full: false,
      details: [{ coveredDays: 30 }],
    })
    expect(
      coverageFor(
        earlier,
        [...accounts, { id: "other", label: "Other" }],
        covered
      ).full
    ).toBe(false)
    expect(
      coverageFor(earlier, accounts, { ...covered, truncated: true }).full
    ).toBe(false)
    expect(
      coverageFor(earlier, accounts, { ...covered, available: false }).full
    ).toBe(false)
    expect(
      coverageFor(earlier, accounts, {
        ...covered,
        periods: [{ ...covered.periods[0], incomplete: true }],
      }).full
    ).toBe(false)
  })
  it("preserves exact money and driver attribution including zero baselines and decreases", () => {
    const before = [
      row("a", "2021-01-05", "9007199254740993", "Vendor A"),
      row("b", "2021-01-06", "200", "Vendor B"),
    ]
    const after = [
      row("c", "2021-02-05", "9007199254741093", "Vendor A"),
      row("d", "2021-02-06", "50", "Vendor C"),
    ]
    const result = investigateTrends(
      [...before, ...after],
      "USD:bank",
      earlier,
      later,
      covered
    )
    expect(result.comparable).toBe(true)
    expect(result.totals[1]).toMatchObject({
      before: 9007199254741193n,
      after: 9007199254741143n,
    })
    const drivers = changeDrivers(before, after, "debit", "name")
    expect(drivers.map((d) => [d.name, d.delta])).toEqual([
      ["Vendor B", -200n],
      ["Vendor A", 100n],
      ["Vendor C", 50n],
    ])
    expect(drivers.reduce((s, d) => s + d.delta, 0n)).toBe(-50n)
    expect(changePercent(0n, 100n)).toBeNull()
    expect(changePercent(200n, 100n)).toBe("−50.0%")
  })
  it("does not blend currencies or cards and suppresses completeness with unusable readings", () => {
    expect(() =>
      investigateTrends(
        [
          row("a", "2021-01-01"),
          row("b", "2021-02-01", "100", "Vendor", { currency: "EUR" }),
        ],
        "USD:bank",
        earlier,
        later,
        covered
      )
    ).toThrow(/one currency/)
    const result = investigateTrends(
      [
        row("undated", "2021-02-28", "100", "Vendor", {
          ordering_date_context: "statement_end_ordering_only",
        }),
        row("unsafe", "2021-02-03", "100", "Vendor", {
          amount_minor: Number.MAX_SAFE_INTEGER + 1,
        }),
        row("valid", "2021-02-10"),
      ],
      "USD:bank",
      earlier,
      later,
      covered
    )
    expect(result.comparable).toBe(false)
    expect(result.unknownDates.map((r) => r.key)).toEqual(["undated"])
    expect(result.invalidAmounts.map((r) => r.key)).toEqual(["unsafe"])
    expect(result.after.map((r) => r.key)).toEqual(["valid"])
  })
  it("first-seen means absent from all earlier loaded history and never promotes missing names", () => {
    const rows = [
      row("old", "2020-12-01", "100", "Known"),
      row("prior", "2021-01-03", "100", "Other"),
      row("known", "2021-02-03", "100", "Known"),
      row("new", "2021-02-04", "100", "New"),
      row("missing", "2021-02-05", "100", ""),
    ]
    expect(
      trendObservations(rows, earlier, later)
        .filter((o) => o.kind === "first-seen")
        .map((o) => o.title)
    ).toEqual(["New"])
    expect(
      trendObservations(rows.slice(2), earlier, later).filter(
        (o) => o.kind === "first-seen"
      )
    ).toEqual([])
  })
  it("recognises a monthly recurrence using older history and requires one account, name and equal amount", () => {
    const rows = [
      row("r1", "2020-12-10", "1299", "Subscription"),
      row("r2", "2021-01-10", "1299", "Subscription"),
      row("r3", "2021-02-10", "1299", "Subscription"),
    ]
    expect(
      trendObservations(rows, earlier, later)
        .find((o) => o.kind === "recurring")
        ?.rows.map((r) => r.key)
    ).toEqual(["r1", "r2", "r3"])
    for (const change of [
      { account_id: "other" },
      { to_name: "Different" },
      { amount_minor: "1300" },
      { ordering_date: "2021-02-24" },
    ])
      expect(
        trendObservations(
          [...rows.slice(0, 2), { ...rows[2], ...change }],
          earlier,
          later
        ).filter((o) => o.kind === "recurring")
      ).toEqual([])
    expect(
      trendObservations(
        [...rows, { ...rows[2], key: "duplicate" }],
        earlier,
        later
      ).filter((o) => o.kind === "recurring")
    ).toEqual([])
  })
  it("uses a per-account direction baseline with at least five observations and an exact median", () => {
    const prior = [100, 101, 102, 103, 104, 105].map((n, i) =>
      row(`a${i}`, `2021-01-0${i + 1}`, String(n))
    )
    const result = trendObservations(
      [
        ...prior,
        row("large", "2021-02-03", "400"),
        row("other", "2021-02-03", "9999", "Vendor", { account_id: "other" }),
      ],
      earlier,
      later
    ).filter((o) => o.kind === "larger")
    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      rows: [{ key: "large" }],
      baseline: { medianTwice: 205n, maximum: 105n, count: 6 },
    })
    expect(
      trendObservations(
        [...prior.slice(0, 4), row("large", "2021-02-03", "400")],
        earlier,
        later
      ).filter((o) => o.kind === "larger")
    ).toEqual([])
  })
  it("matches returns by reference and exact amount, rejecting ambiguous or reversed pairs", () => {
    const debit = row("out", "2021-02-22", "1305000", "", {
      description: "T17 SPID ENVIADO BANORTE Ref. 0004700971 072",
      row_index: 1,
      statement_period_id: "period",
    })
    const credit = row("back", "2021-02-22", "1305000", "Owner", {
      description: "T22 SPID DEVUELTOBANORTE Ref. 0004700971 072",
      direction: "credit",
      from_name: "",
      row_index: 2,
      statement_period_id: "period",
    })
    const returns = (rows: LedgerTransaction[]) =>
      trendObservations(rows, earlier, later).filter((o) => o.kind === "return")
    expect(returns([debit, credit])[0]?.rows.map((r) => r.key)).toEqual([
      "out",
      "back",
    ])
    expect(returns([debit, credit, { ...debit, key: "ambiguous" }])).toEqual([])
    expect(
      returns([debit, credit, { ...credit, key: "duplicate-credit" }])
    ).toEqual([])
    expect(returns([{ ...debit, row_index: 3 }, credit])).toEqual([])
    expect(returns([debit, { ...credit, amount_minor: "1305001" }])).toEqual([])
  })
})
