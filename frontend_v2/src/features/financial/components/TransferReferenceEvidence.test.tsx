import { render, screen, fireEvent, cleanup } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { TransferReferenceEvidence } from "./TransferReferenceEvidence"
import type { TransferInputs } from "../lib/ledger-transfers"
afterEach(cleanup)
it("pages identifier evidence and opens both retained sources, including conflicts", () => {
  const onSource = vi.fn()
  const data = {
    unscoped_reference_ids: ["unscoped"],
    reference_evidence: Array.from({ length: 11 }, (_, i) => ({
      left_id: `l${i}`,
      right_id: `r${i}`,
      reference: {
        kind: "uuid",
        value: `reference${i}`,
        scope: "global",
        scope_key: null,
      },
      relation: "conflict",
      amounts_agree: false,
      reason: "Different readings remain separate.",
    })),
  } as TransferInputs
  render(<TransferReferenceEvidence data={data} onSource={onSource} />)
  expect(screen.getAllByRole("article")).toHaveLength(10)
  fireEvent.click(screen.getByRole("button", { name: "Next identifiers" }))
  expect(screen.getAllByRole("article")).toHaveLength(1)
  fireEvent.click(
    screen.getByRole("button", { name: "First identifier source 11" })
  )
  fireEvent.click(
    screen.getByRole("button", { name: "Second identifier source 11" })
  )
  expect(onSource.mock.calls).toEqual([["l10"], ["r10"]])
  expect(
    screen.getByText(/Conflicting account or direction/)
  ).toBeInTheDocument()
  expect(screen.getByText(/1 readings have references/)).toBeInTheDocument()
})
