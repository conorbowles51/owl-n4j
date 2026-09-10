import { render, screen } from "@testing-library/react"
import { expect, it } from "vitest"
import { nativeControlComparison } from "../lib/native-control-contract"
import { NativeControlComparisonPanel } from "./NativeControlComparisonPanel"
const current = {
  format: "nacha",
  mapped_rows: 1,
  unmapped_rows_retained: 0,
  basis: "Unchanged source controls",
  changes_proof_class: false,
  checks: [
    {
      scope: "batch:0",
      kind: "control",
      result: {
        status: "balanced",
        credit_delta: { minor_units: "0", currency: "USD" },
      },
    },
  ],
}
const capture = {
  available: true,
  sha256: "a".repeat(64),
  parser_name: "nacha",
  parser_version: "test",
  date_context: {
    earliest: "2026-01-01",
    latest: "2026-01-31",
    basis: "Recorded context",
  },
  current,
  proposed: {
    ...current,
    checks: [
      {
        scope: "batch:0",
        kind: "control",
        result: {
          status: "unbalanced",
          credit_delta: { minor_units: "9007199254740993", currency: "USD" },
        },
      },
    ],
  },
  current_transaction_ids: ["row"],
  limitation: "Conditional arithmetic; proof class unchanged.",
}
it("shows before and after discrepancies with exact source context", () => {
  render(
    <NativeControlComparisonPanel
      comparison={nativeControlComparison.parse(capture)}
    />
  )
  expect(screen.getByText("Before correction")).toBeInTheDocument()
  expect(screen.getByText("After proposed correction")).toBeInTheDocument()
  expect(screen.getByText("batch:0 · control: unbalanced")).toBeInTheDocument()
  expect(
    screen.getByText("9007199254740993 minor units (USD)")
  ).toBeInTheDocument()
})
it("distinguishes unavailable checks from balanced controls", () => {
  render(
    <NativeControlComparisonPanel
      comparison={{ available: false, reason: "Source bytes changed" }}
    />
  )
  expect(screen.getByRole("status")).toHaveTextContent("Source bytes changed")
  expect(screen.queryByText("Before correction")).not.toBeInTheDocument()
})
it("refuses an unknown status or proof promotion", () => {
  expect(
    nativeControlComparison.safeParse({
      ...capture,
      current: { ...current, changes_proof_class: true },
    }).success
  ).toBe(false)
  expect(
    nativeControlComparison.safeParse({
      ...capture,
      current: {
        ...current,
        checks: [
          { scope: "file", kind: "control", result: { status: "verified" } },
        ],
      },
    }).success
  ).toBe(false)
})
