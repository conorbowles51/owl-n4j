import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { StatementLayoutContextPanel } from "./StatementLayoutContextPanel"
import type { StatementLayoutContext } from "../lib/statement-layout-context"
const cite = (text: string, row = 0) => ({
  row_index: row,
  column_index: 0,
  expected_text: text,
  locator: { kind: "page_only", page: 3 },
})
function fixture(): StatementLayoutContext {
  return {
    layout_id: "capital-one-platinum-card-sections",
    version: 1,
    institution_source: cite("Capital One"),
    printed_card_source: cite("Ending in 3539"),
    cycle_source: cite(
      "May 12, 2020 - Jun. 11, 2020 | 31 days in Billing Cycle"
    ),
    start_date: "2020-05-12",
    end_date: "2020-06-11",
    applied: false,
    limitation: "Proposals only; no fields are filled.",
    rows: [
      {
        row_index: 9,
        card_ending: "3539",
        printed_section: "Payments, Credits and Adjustments",
        section_source: cite(
          "PERSON #3539: Payments, Credits and Adjustments",
          7
        ),
        date_source: cite("May 30", 9),
        date_label: "Date",
        posting_date_proposals: [],
        description_source: cite("PAYMENT", 9),
        amount_source: cite("- $180.00", 9),
        date_proposals: ["2020-05-30"],
        direction: null,
        requires_source_review: true,
      },
    ],
  }
}
it("keeps context optional and opens the exact section, cycle and amount sources", () => {
  const context = fixture(),
    onSource = vi.fn()
  render(<StatementLayoutContextPanel context={context} onSource={onSource} />)
  expect(screen.queryByRole("region")).toBeNull()
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect printed statement context" })
  )
  expect(
    screen.getByText(/Possible date within this cycle: 2020-05-30/)
  ).toBeTruthy()
  expect(screen.getByText(/does not determine money direction/)).toBeTruthy()
  for (const [button, source] of [
    ["Inspect printed billing cycle", context.cycle_source],
    ["Inspect section for row 10", context.rows[0].section_source],
    ["Inspect amount for row 10", context.rows[0].amount_source],
  ] as const) {
    fireEvent.click(screen.getByRole("button", { name: button }))
    expect(onSource).toHaveBeenLastCalledWith(source)
  }
  expect(screen.queryAllByRole("textbox")).toHaveLength(0)
})
it("does not invent a year for a date outside the printed cycle", () => {
  const context = fixture()
  context.rows[0].date_proposals = []
  render(<StatementLayoutContextPanel context={context} onSource={() => {}} />)
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect printed statement context" })
  )
  expect(screen.getByText(/date remains unresolved/)).toBeTruthy()
})
