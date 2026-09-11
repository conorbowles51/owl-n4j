import { expect, it } from "vitest"
import { reviewSelectionBalance } from "./statement-review-balance"
const originals: { id: string; kind: string; fields: Record<string, string> }[] = [
  { id: "o", kind: "balance", fields: { description: "Opening Balance" } },
  { id: "a", kind: "transaction", fields: { date: "2023-01-02" } },
  { id: "b", kind: "transaction", fields: { date: "2023-01-03" } },
]
const rows = [
  {
    id: "o",
    excluded: true,
    amount_minor: "0",
    direction: "credit" as const,
    balance_minor: "10000",
  },
  {
    id: "a",
    excluded: false,
    amount_minor: "5000",
    direction: "credit" as const,
    balance_minor: "15000",
  },
  {
    id: "b",
    excluded: false,
    amount_minor: "2000",
    direction: "debit" as const,
    balance_minor: "13000",
  },
]
it("recalculates after excluding or correcting a payment without losing the printed endpoint", () => {
  expect(reviewSelectionBalance(rows, originals, false)?.difference).toBe("0")
  expect(
    reviewSelectionBalance(
      rows.map((row) => (row.id === "a" ? { ...row, excluded: true } : row)),
      originals,
      false
    )?.difference
  ).toBe("-5000")
  expect(
    reviewSelectionBalance(
      rows.map((row) =>
        row.id === "b" ? { ...row, amount_minor: "2100" } : row
      ),
      originals,
      false
    )?.difference
  ).toBe("-100")
  expect(
    reviewSelectionBalance(
      rows.map((row) => (row.id === "b" ? { ...row, excluded: true } : row)),
      originals,
      false
    )?.difference
  ).toBe("2000")
  expect(reviewSelectionBalance(rows, originals, false)?.independent).toBe(
    false
  )
})
it("does not invent an opening control or a sequence for descending source rows", () => {
  expect(reviewSelectionBalance(rows, originals.slice(1), false)).toBeNull()
  expect(
    reviewSelectionBalance(
      rows,
      [originals[0], originals[2], originals[1]],
      false
    )
  ).toBeNull()
})
