import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import type { LedgerTransaction } from "../api"
import { TableColumnPicker, TransactionExplorerTable } from "./TransactionExplorerTable"
import { readTableColumns, storeTableColumns, type OptionalColumn } from "../lib/table-columns"
import { useState } from "react"
import { patternAPI } from "@/features/pattern/api"

vi.mock("./JudgementCalls", () => ({ RowJudgementMarkers: () => null }))
afterEach(() => {
  cleanup()
  localStorage.clear()
})
const row = {
  key: "t1", ref_id: "TX-EMBH", bank_reference: "BR-9", account_id: "a1", account_label: "BBVA 0118",
  running_balance_minor: "150000", currency: "MXN", source_document_id: "doc-1", proof_class: "p1",
  direction: "debit", amount_minor: "2500", ordering_date: "2023-10-31", ordering_date_context: "transaction",
  description: "PAGO", category: "Payments",
} as unknown as LedgerTransaction

function Harness() {
  const [columns, setColumns] = useState<OptionalColumn[]>(readTableColumns)
  return (
    <>
      <TableColumnPicker columns={columns} onChange={(next) => { setColumns(next); storeTableColumns(next) }} />
      <TransactionExplorerTable rows={[row]} selected={[]} expanded={[]} sort="newest" onSort={vi.fn()} onExpand={vi.fn()}
        onToggle={vi.fn()} onParty={vi.fn()} columns={columns} statementNames={new Map([["doc-1", "08 BBVA AGO 2023.pdf"]])}
        amountAllowed={false} />
    </>
  )
}

it("adds optional columns from the picker, remembers them, and resets to the default", () => {
  render(<Harness />)
  expect(screen.getByText("Choose one currency to sort amounts")).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: /Columns \(6 of 13\)/ }))
  for (const name of ["Reference", "Bank reference", "Statement", "How it was read", "Printed balance"])
    fireEvent.click(screen.getByRole("checkbox", { name }))
  expect(screen.getByRole("button", { name: /Columns \(11 of 13\)/ })).toBeTruthy()
  expect(screen.getByRole("columnheader", { name: "Statement" })).toBeTruthy()
  expect(screen.getByText("TX-EMBH")).toBeTruthy()
  expect(screen.getByText("BR-9")).toBeTruthy()
  expect(screen.getByText("08 BBVA AGO 2023.pdf")).toBeTruthy()
  expect(readTableColumns()).toEqual(["reference", "bank_reference", "balance", "statement", "proof"])
  fireEvent.click(screen.getByRole("button", { name: "Reset to default" }))
  expect(screen.queryByRole("columnheader", { name: "Statement" })).toBeNull()
  expect(readTableColumns()).toEqual([])
})

it("an open payment shows the place section, so a place can be attached where the payment is read (04 8.5)", async () => {
  const key = "11111111-2222-3333-4444-555555555555"
  vi.spyOn(patternAPI, "manualPlaces").mockResolvedValue({ total: 0, items: [] })
  render(<TransactionExplorerTable caseId="c" rows={[{ ...row, key }]} selected={[]} expanded={[key]} sort="newest" onSort={vi.fn()}
    onExpand={vi.fn()} onToggle={vi.fn()} onParty={vi.fn()} columns={[]} statementNames={new Map()} amountAllowed={false} />)
  expect(await screen.findByRole("button", { name: "Attach a place" })).toBeTruthy()
  vi.restoreAllMocks()
})
