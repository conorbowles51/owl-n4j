import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { StatementCoverageReview } from "./StatementCoverageReview"

afterEach(cleanup)

const review = {
  available: true,
  revision: "rev",
  matching_statement: true,
  repeated_activity: true,
  candidates: [
    {
      file_id: "f",
      filename: "earlier.pdf",
      status: "imported" as const,
      period_start: "2022-06-01",
      period_end: "2022-06-30",
      matching_statement: true,
      repeated_activity: {
        repeated: 2,
        with_printed_reference: 1,
        own_rows: 40,
        other_rows: 38,
        carried_balance: "A line carries the earlier closing balance",
        other_number: "4120 6180 6507 0753",
        other_holder: "HOLDER",
        examples: [
          {
            date: "2022-06-30",
            amount_minor: "15000",
            direction: "debit",
            currency: "USD",
            description: "MOBILE PAYMENT",
            printed_reference_matches: true,
          },
        ],
      },
    },
  ],
}

it("holds a statement repeating earlier activity as a suggestion, naming what matches", () => {
  render(
    <StatementCoverageReview
      onCompare={vi.fn()}
      review={review}
      decision={{ revision: "", reason: "" }}
      change={vi.fn()}
      canEdit
      inBatch={false}
    />
  )
  expect(screen.getByRole("heading", { name: "Possible repeated activity — import on hold" })).toBeVisible()
  expect(screen.getByText(/This is a suggestion from matching printed values, not a finding/)).toBeVisible()
  expect(screen.getByText(/Nothing has been removed from either statement/)).toBeVisible()
  expect(
    screen.getByText("2 of 40 payments here match this statement under number 4120 6180 6507 0753, 1 with the same printed reference.")
  ).toBeVisible()
  expect(screen.getByText("A line carries the earlier closing balance.")).toBeVisible()
  expect(screen.getByText(/2022-06-30 · 150\.00 USD · MOBILE PAYMENT/)).toBeVisible()
  expect(screen.queryByText(/Same account, holder, currency and period/)).toBeNull()
})

it("keeps the existing wording for a statement that only overlaps", () => {
  render(
    <StatementCoverageReview
      onCompare={vi.fn()}
      review={{ ...review, repeated_activity: undefined, matching_statement: false, candidates: [{ ...review.candidates[0], matching_statement: false, repeated_activity: undefined }] }}
      decision={{ revision: "", reason: "" }}
      change={vi.fn()}
      canEdit
      inBatch={false}
    />
  )
  expect(screen.getByRole("heading", { name: "Another statement covers these dates" })).toBeVisible()
})

it("opens the side-by-side compare with the chosen statement", () => {
  const onCompare = vi.fn()
  render(
    <StatementCoverageReview
      onCompare={onCompare}
      review={review}
      decision={{ revision: "", reason: "" }}
      change={vi.fn()}
      canEdit
      inBatch={false}
    />
  )
  expect(screen.queryByRole("button", { name: "Compare original PDF" })).toBeNull()
  fireEvent.click(screen.getByRole("button", { name: "Compare side by side" }))
  expect(onCompare).toHaveBeenCalledWith(review.candidates[0])
})
