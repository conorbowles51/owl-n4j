import { render, screen, fireEvent } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { StatementScopeEditor } from "./StatementScopeEditor"
import {
  signedControlMinor,
  statementScope,
} from "../lib/statement-scope-contract"
vi.mock("./StatementEditorDraftPanel", () => ({ StatementEditorDraftPanel: () => null }))
vi.mock("./StatementControlPicker", () => ({
  StatementControlPicker: ({
    onSelected,
  }: {
    onSelected: (value: unknown) => void
  }) => (
    <button
      onClick={() =>
        onSelected({
          page_number: 1,
          table_index: 0,
          row_index: 0,
          column_index: 0,
          source_revision: "a".repeat(64),
          expected_text: "Printed control",
        })
      }
    >
      Pick control source
    </button>
  ),
}))
const account = "9445f4da-ed83-4819-9ce2-059cb259790a",
  candidate = "7b74f9db-9ff4-4325-a966-ddda8e957879"
function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } })
}
function mount() {
  const save = vi.fn()
  render(
    <StatementScopeEditor
      caseId="case"
      fileId="file"
      readings={[
        {
          candidate_id: candidate,
          account_id: account,
          currency: "USD",
          account_label: "Test account",
          booking_date: "2026-02-01",
          transaction_date: null,
          description: "Payment",
        },
      ]}
      onSave={save}
      onClose={vi.fn()}
    />
  )
  return save
}
function basics() {
  fill("Statement account", `${account}:USD`)
  fireEvent.click(screen.getByLabelText("Assign reviewed row 1 to statement"))
  fill("Printed statement start", "2026-02-01")
  fill("Printed statement end", "2026-02-28")
  fill("Printed balance convention", "liability_owed")
  fill(
    "Reason for statement control readings",
    "Visually checked printed controls"
  )
}
function source(label: string) {
  fireEvent.click(
    screen.getByRole("button", { name: `Choose source for ${label}` })
  )
  fireEvent.click(screen.getByRole("button", { name: "Pick control source" }))
}
it("requires original date sources and keeps absent balances unknown", () => {
  const save = mount()
  basics()
  expect(
    screen.getByRole("button", { name: "Add statement to preview" })
  ).toBeDisabled()
  source("statement start")
  source("statement end")
  fireEvent.click(
    screen.getByRole("button", { name: "Add statement to preview" })
  )
  expect(save).toHaveBeenCalledTimes(1)
  expect(save.mock.calls[0][0]).toMatchObject({
    opening: null,
    closing: null,
    balance_convention: "liability_owed",
    candidate_ids: [candidate],
    start: { source: { expected_text: "Printed control" } },
  })
})
it("requires source cells for entered balances and preserves exact printed signs", () => {
  const save = mount()
  basics()
  source("statement start")
  source("statement end")
  fill("Printed opening balance", "90071992547409.93")
  fill("Printed closing balance", "-10.00")
  expect(
    screen.getByRole("button", { name: "Add statement to preview" })
  ).toBeDisabled()
  source("opening balance")
  source("closing balance")
  fireEvent.click(
    screen.getByRole("button", { name: "Add statement to preview" })
  )
  expect(save.mock.calls[0][0]).toMatchObject({
    opening: { amount_minor: "9007199254740993" },
    closing: { amount_minor: "-1000" },
  })
})
it("refuses reversed dates and clears assigned rows when account choice changes", () => {
  mount()
  basics()
  source("statement start")
  source("statement end")
  fill("Printed statement start", "2026-03-01")
  expect(
    screen.getByRole("button", { name: "Add statement to preview" })
  ).toBeDisabled()
  fill("Statement account", "")
  expect(
    screen.queryByLabelText("Assign reviewed row 1 to statement")
  ).not.toBeInTheDocument()
})
it("does not round unsupported decimals or silently discard a sign", () => {
  expect(signedControlMinor("-0.01", "USD")).toBe("-1")
  expect(signedControlMinor("1.234", "USD")).toBeNull()
  expect(signedControlMinor("-0.00", "USD")).toBe("0")
  expect(statementScope.safeParse({}).success).toBe(false)
})
