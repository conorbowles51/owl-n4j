import { expect, it } from "vitest"
import {
  historyMonths,
  accountColor,
  type HistoryGroup,
  type HistoryPeriod,
} from "./account-history"
const period = (
  start: string,
  end: string,
  overrides: Partial<HistoryPeriod> = {}
): HistoryPeriod => ({
  id: start,
  source_document_id: start,
  evidence_file_id: start,
  filename: "Synthetic.pdf",
  start,
  end,
  opening_minor: "5000000",
  closing_minor: "5000000",
  status: "confirmed_no_activity",
  transaction_count: 0,
  undated_count: 0,
  activity: [],
  ...overrides,
})
const group = (periods: HistoryPeriod[]): HistoryGroup => ({
  key: "a",
  account_id: "a",
  currency: "MXN",
  balance_kind: "asset",
  label: "Example Bank 001",
  periods,
})
it("keeps quiet months, missing coverage and bursts distinct without inventing balances", () => {
  const data = historyMonths([
    group([
      period("2026-01-01", "2026-01-31"),
      period("2026-03-01", "2026-03-31", {
        status: "reconciled",
        transaction_count: 2,
        closing_minor: "5050000",
        activity: [
          {
            date: "2026-03-05",
            count: 2,
            credit_minor: "100000",
            debit_minor: "50000",
          },
        ],
      }),
    ]),
  ])
  expect(data.map((m) => m.values[0].count)).toEqual([0, 2])
  expect(data.map((m) => m.values[0].closing_minor)).toEqual([
    "5000000",
    "5050000",
  ])
  expect(data.map((m) => m.month)).toEqual(["2026-01", "2026-03"])
})
it("does not turn unreadable or partial zero-payment periods into confirmed no activity", () => {
  const data = historyMonths(
    [
      group([
        period("2026-01-15", "2026-01-31"),
        period("2026-02-01", "2026-02-28", { status: "needs_review" }),
      ]),
    ],
    "2026-01-01"
  )
  expect(data.map((m) => m.values[0].count)).toEqual([null, null])
})
it("uses transaction dates within multi-month statements and flags unprinted dates", () => {
  const data = historyMonths([
    group([
      period("2026-01-01", "2026-03-31", {
        status: "reconciled",
        transaction_count: 1,
        activity: [
          {
            date: "2026-02-10",
            count: 1,
            credit_minor: "1234567890123456789",
            debit_minor: "0",
          },
        ],
      }),
    ]),
  ])
  expect(data.map((m) => m.values[0].count)).toEqual([0, 1, 0])
  expect(data[1].values[0].credit_minor).toBe("1234567890123456789")
  expect(
    historyMonths([
      group([period("2026-01-01", "2026-01-31", { undated_count: 1 })]),
    ])[0].values[0].count
  ).toBeNull()
})
it("does not sum overlapping balances or double count overlapping source activity", () => {
  const p = period("2026-01-01", "2026-01-31")
  const value = historyMonths([group([p, { ...p, id: "duplicate" }])])[0]
    .values[0]
  expect(value.count).toBeNull()
  expect(value.closing_minor).toBeNull()
  expect(value.state).toMatch(/Overlapping/)
  expect(accountColor("a")).toBe(accountColor("a"))
})

it("uses represented-month union and leaves unsupported comparison accounts unavailable", () => {
  const data = historyMonths(
    [
      group([
        period("2025-10-01", "2025-11-30"),
        period("2026-01-01", "2026-01-31"),
      ]),
      {
        ...group([period("2025-10-01", "2025-10-31")]),
        key: "b",
        account_id: "b",
      },
    ],
    "2025-01-01",
    "2026-12-31"
  )
  expect(data.map((m) => m.month)).toEqual(["2025-10", "2025-11", "2026-01"])
  expect(data[1].values[0].count).toBe(0)
  expect(data[1].values[1]).toMatchObject({
    count: null,
    closing_minor: null,
    state: "No statement available",
  })
})
it("keeps actual dated payments when the statement's period dates are missing", () => {
  const data = historyMonths([
    group([
      period("2025-10-01", "2025-10-31", {
        start: null,
        end: null,
        status: "needs_review",
        activity: [
          {
            date: "2025-11-04",
            count: 1,
            credit_minor: "100",
            debit_minor: "0",
          },
        ],
      }),
    ]),
  ])
  expect(data.map((m) => m.month)).toEqual(["2025-11"])
  expect(data[0].values[0]).toMatchObject({
    count: 1,
    closing_minor: null,
    state: "Partial coverage or unverified reading",
  })
})
