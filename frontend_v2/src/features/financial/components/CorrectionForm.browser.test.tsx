import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { CorrectionForm } from "./CorrectionForm"
import { CorrectionHistory } from "./CorrectionHistory"

afterEach(() => vi.restoreAllMocks())

it("reviews exact held-out amounts and displays both readings in Chromium", async () => {
  const original = {
    key: "old",
    ref_id: "TX-OLD",
    source_document_id: "doc",
    amount_minor: "9007199254740993",
    currency: "GBP",
    direction: "debit",
  }
  const replacement = {
    ...original,
    key: "new",
    ref_id: "TX-NEW",
    amount_minor: "9007199254740994",
  }
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          case_id: "case-1",
          transaction_id: "old",
          document_revision: "a".repeat(64),
          applied: false,
          original,
          proposed: {
            amount_minor: replacement.amount_minor,
            currency: "GBP",
            direction: "debit",
            ledger_status: "quarantined",
          },
          statement_identity: null,
          limitation: "No linked statement period.",
          verification: {
            can_record: true,
            current_proof_class: "p2",
            proposed_proof_class: "p2",
            reservations: [],
            included_in_default_totals: true,
            scope: "document",
            reason: null,
          },
        })
      )
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          case_id: "case-1",
          transaction_id: "old",
          replacement_id: "new",
          replacement_ref_id: "TX-NEW",
          adjudication_id: "event",
          applied: true,
          proof_class: "p2",
          ledger_status: "quarantined",
        })
      )
    )
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CorrectionForm
        caseId="case-1"
        transactionId="old"
        currency="GBP"
        initialDirection="debit"
        onClose={vi.fn()}
      />
    </QueryClientProvider>
  )
  fireEvent.change(screen.getByLabelText("Proposed amount (GBP)"), {
    target: { value: "90071992547409.94" },
  })
  fireEvent.change(screen.getByLabelText("Reason for correction"), {
    target: { value: "Synthetic exact-money check" },
  })
  expect(
    screen.getByRole("button", { name: "Record correction" })
  ).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Preview correction" }))
  expect(
    await screen.findByText(/Original TX-OLD: 90071992547409.93 GBP debit/)
  ).toBeVisible()
  expect(
    screen.getByText(
      "The replacement remains quarantined and excluded from totals."
    )
  ).toBeVisible()
  const record = screen.getByRole("button", { name: "Record correction" })
  fireEvent.click(record)
  fireEvent.click(record)
  expect(await screen.findByRole("status")).toHaveTextContent("TX-NEW")
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toEqual({
    amount_minor: "9007199254740994",
    direction: "debit",
    expected_revision: "a".repeat(64),
    reason: "Synthetic exact-money check",
  })
  render(
    <CorrectionHistory
      before={{ row: original }}
      after={{ row: replacement }}
    />
  )
  fireEvent.click(screen.getByText("Original and replacement readings"))
  expect(
    screen.getByText(/Replacement TX-NEW: 90071992547409.94 GBP debit/)
  ).toBeVisible()
})
