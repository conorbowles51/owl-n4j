import { expect, it } from "vitest"
import type { Transaction } from "../api"
import {
  evidenceAmountCents,
  formatEvidenceCents,
  summarizeEvidenceAmounts,
} from "./evidence-amounts"
import { buildEvidenceVolumeData } from "./evidence-chart-data"

function row(
  amount: number,
  currency = "EUR",
  category = "Review"
): Transaction {
  return {
    key: String(amount),
    amount,
    currency,
    category,
    date: "2026-09-02",
    financial_record_kind: "other",
    financial_view_mode: "intelligence",
    is_financial_event: false,
    is_evidence_backed_transaction: false,
  } as Transaction
}
it("adds decimal amounts exactly and keeps positive, negative, unknown and different currencies apart", () => {
  const result = summarizeEvidenceAmounts([
    row(0.1),
    row(0.2),
    row(-0.15),
    row(50, "USD"),
    row(1000, ""),
  ])
  expect(result.find((group) => group.currency === "EUR")).toMatchObject({
    count: 3,
    positive: 30n,
    negative: -15n,
    incomplete: false,
  })
  expect(result.find((group) => group.currency === "USD")).toMatchObject({
    positive: 5000n,
    negative: 0n,
  })
  expect(
    result.find((group) => group.currency === "Currency not recorded")
  ).toMatchObject({ count: 1, incomplete: true })
  expect(formatEvidenceCents(-123450n)).toBe("-1,234.50")
})
it("refuses unsafe, non-finite and excess-precision amounts instead of rounding totals", () => {
  for (const value of [Infinity, NaN, 1.234, Number.MAX_SAFE_INTEGER])
    expect(evidenceAmountCents(value)).toBeNull()
  expect(summarizeEvidenceAmounts([row(1.234)])[0].incomplete).toBe(true)
})
it("plots exact amount sizes with safe series keys even for category names containing dots or special properties", () => {
  const result = buildEvidenceVolumeData(
    [
      row(0.1, "EUR", "__proto__"),
      row(-0.2, "EUR", "__proto__"),
      row(1.23, "EUR", "Review.priority"),
    ],
    "daily"
  )
  expect(result.data).toEqual([
    { period: "2026-09-02", category_0: 0.3, category_1: 1.23 },
  ])
  expect(result.categories).toEqual(["__proto__", "Review.priority"])
  expect(result.tooLarge).toBe(false)
})
it("does not convert an oversized period total to a rounded chart number", () => {
  const result = buildEvidenceVolumeData(
    [row(50000000000000), row(50000000000000)],
    "daily"
  )
  expect(result.tooLarge).toBe(true)
  expect(result.data).toEqual([])
})

it("keeps month and week grouping on the recorded calendar dates", () => {
  const records = [{ ...row(1), date: "2026-09-01" }]
  expect(buildEvidenceVolumeData(records, "monthly").data[0].period).toBe(
    "2026-09"
  )
  expect(buildEvidenceVolumeData(records, "weekly").data[0].period).toBe(
    "2026-08-30"
  )
})
