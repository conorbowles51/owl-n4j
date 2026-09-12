import { expect, it } from "vitest"
import { reviewSelectionBalance } from "./statement-review-balance"
const originals: {
  id: string
  kind: string
  fields: Record<string, string>
}[] = [
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

it("compares printed amounts owed using charges minus payments and keeps corrections separate", () => {
  const cardOriginals = [
    ...originals,
    { id: "interest", kind: "transaction", fields: {} },
    {
      id: "close",
      kind: "balance",
      fields: { description: "Closing Balance" },
    },
  ]
  const cardRows = [
    { ...rows[0], balance_minor: "100000" },
    { ...rows[1], amount_minor: "18000", balance_minor: null },
    { ...rows[2], amount_minor: "6162", balance_minor: null },
    { ...rows[2], id: "interest", amount_minor: "5616", balance_minor: null },
    { ...rows[0], id: "close", balance_minor: "93778" },
  ]
  expect(reviewSelectionBalance(cardRows, cardOriginals, true)).toMatchObject({
    expected: "93778",
    printed: "93778",
    difference: "0",
    independent: true,
  })
  expect(
    reviewSelectionBalance(
      cardRows.map((r) =>
        r.id === "close" ? { ...r, balance_minor: "93878" } : r
      ),
      cardOriginals,
      true
    )?.difference
  ).toBe("-100")
  expect(
    reviewSelectionBalance(
      cardRows.map((r) => (r.id === "interest" ? { ...r, excluded: true } : r)),
      cardOriginals,
      true
    )?.difference
  ).toBe("-5616")
})
