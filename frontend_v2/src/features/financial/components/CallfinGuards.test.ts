import { readFileSync } from "node:fs"
import { expect, it } from "vitest"
import { PRIORITY_LABELS } from "../lib/judgements"
import { readLedgerStatus } from "../lib/ledger-format"

const source = (file: string) => readFileSync(new URL(file, import.meta.url), "utf8")

it("FIN-06: the check-first ordering keeps its three tiers in order", () => {
  expect(Object.entries(PRIORITY_LABELS)).toEqual([
    ["1", "Check first"],
    ["2", "Check soon"],
    ["3", "When convenient"],
  ])
})
it("FIN-05: an included payment is not called 'Admitted' on its own above a warning", () => {
  expect(readLedgerStatus("admitted").label).toBe("Included")
  expect(source("./LedgerSourceDialog.tsx")).toContain("`Included — ${")
})
it("FIN-09: users read 'counterparty not identified', never 'other side not identified'", () => {
  for (const file of ["./LedgerRowBrowser.tsx", "./InvestigatorPeople.tsx"])
    expect(source(file)).not.toMatch(/other side not identified/i)
  expect(source("./LedgerRowBrowser.tsx")).toMatch(/counterparty not identified/)
})
it("FIN-24: payments and findings can still be added to the timeline", () => {
  expect(source("./LedgerRowBrowser.tsx")).toContain("Add to Timeline")
  expect(source("./FinancialFindingCard.tsx")).toContain("Add to Timeline")
})
it("FIN-04: the 'Read by … · not confirmed' mark stays in the payment label origin", () => {
  expect(source("./PaymentLabelOrigin.tsx")).toContain("not confirmed")
})
