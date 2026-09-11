import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { CorrectionForm } from "./CorrectionForm"
import {
  correctionMinor,
  correctionMoney,
  correctionPreview,
} from "../lib/correction-contract"

afterEach(() => vi.restoreAllMocks())
const preview = {
  case_id: "case-a",
  transaction_id: "old",
  document_revision: "a".repeat(64),
  applied: false,
  original: {
    key: "old",
    ref_id: "TX-OLD",
    source_document_id: "doc",
    amount_minor: "100",
    currency: "GBP",
    direction: "credit",
  },
  proposed: {
    amount_minor: "200",
    currency: "GBP",
    direction: "credit",
    ledger_status: "admitted",
  },
  statement_identity: {
    current: { status: "balanced", delta_minor: "0" },
    proposed: { status: "unbalanced", delta_minor: "100" },
  },
  limitation: "Statement balance only",
  verification: {
    can_record: true,
    current_proof_class: "p2",
    proposed_proof_class: "p3",
    reservations: [],
    included_in_default_totals: false,
    scope: "document",
    reason: null,
  },
}
function mount(initialDirection: "credit" | "debit" = "credit") {
  const client = new QueryClient()
  const invalidate = vi.spyOn(client, "invalidateQueries")
  render(
    <QueryClientProvider client={client}>
      <CorrectionForm
        caseId="case-a"
        transactionId="old"
        currency="GBP"
        initialDirection={initialDirection}
        onClose={vi.fn()}
      />
    </QueryClientProvider>
  )
  fireEvent.change(screen.getByLabelText("Proposed amount (GBP)"), {
    target: { value: "2.00" },
  })
  fireEvent.change(screen.getByLabelText("Reason for correction"), {
    target: { value: "Reviewed source" },
  })
  return invalidate
}
function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status })
}
it("preserves exact major/minor values and rejects invalid precision", () => {
  expect(correctionMinor("90071992547409.93", "GBP")).toBe("9007199254740993")
  expect(correctionMoney("9007199254740993", "GBP")).toBe(
    "90071992547409.93 GBP"
  )
  expect(correctionMinor("1.234", "BHD")).toBe("1234")
  for (const value of ["1.001", "-1", "1e3", "1,000", "92233720368547758.08"])
    expect(correctionMinor(value, "GBP")).toBeNull()
})
it("requires preview then records exactly once and invalidates the original case", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(response(preview))
    .mockResolvedValueOnce(
      response({
        case_id: "case-a",
        transaction_id: "old",
        replacement_id: "new",
        replacement_ref_id: "TX-NEW",
        adjudication_id: "event",
        applied: true,
        proof_class: "p3",
        ledger_status: "admitted",
      })
    )
  const invalidate = mount()
  expect(
    screen.getByRole("button", { name: "Record correction" })
  ).toBeDisabled()
  fireEvent.click(screen.getByRole("button", { name: "Preview correction" }))
  expect(
    await screen.findByText(
      "This document will be excluded from default verified totals."
    )
  ).toBeVisible()
  const button = screen.getByRole("button", { name: "Record correction" })
  fireEvent.click(button)
  fireEvent.click(button)
  expect(await screen.findByRole("status")).toHaveTextContent("TX-NEW")
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toEqual({
    amount_minor: "200",
    direction: "credit",
    expected_revision: "a".repeat(64),
    reason: "Reviewed source",
  })
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ["financial-ledger", "case-a"],
  })
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ["financial-decisions", "case-a"],
  })
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ["financial-proof-standing", "case-a"],
  })
})
it("preserves a debit direction when editing the magnitude", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    response({
      ...preview,
      original: { ...preview.original, direction: "debit" },
      proposed: { ...preview.proposed, direction: "debit" },
    })
  )
  mount("debit")
  expect(screen.getByLabelText("Direction")).toHaveValue("debit")
  fireEvent.click(screen.getByRole("button", { name: "Preview correction" }))
  await screen.findByText(/Original TX-OLD/)
  expect(JSON.parse(String(fetch.mock.calls[0][1]?.body)).direction).toBe(
    "debit"
  )
})
it("withholds confirmation when the source cannot be classified", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    response({
      ...preview,
      verification: {
        ...preview.verification,
        can_record: false,
        proposed_proof_class: null,
        reason: "Unknown source shape",
      },
    })
  )
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Preview correction" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Unknown source shape"
  )
  expect(
    screen.getByRole("button", { name: "Record correction" })
  ).toBeDisabled()
  expect(
    screen.queryByText(
      "This document will be excluded from default verified totals."
    )
  ).toBeNull()
})
it.each([
  { included_in_default_totals: true },
  { proposed_proof_class: null },
  {
    proposed_proof_class: "p2",
    included_in_default_totals: true,
    reservations: ["Native controls not checked"],
  },
  { can_record: false, proposed_proof_class: null, reason: "" },
  { reason: "Recording is not possible" },
])(
  "refuses inconsistent verification before confirmation (%j)",
  async (verification) => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response({
        ...preview,
        verification: { ...preview.verification, ...verification },
      })
    )
    mount()
    fireEvent.click(screen.getByRole("button", { name: "Preview correction" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Preview unavailable"
    )
    expect(
      screen.getByRole("button", { name: "Record correction" })
    ).toBeDisabled()
    expect(fetch).toHaveBeenCalledTimes(1)
  }
)
it("rejects malformed original magnitudes instead of displaying invented money", () => {
  for (const amount_minor of ["-1", "01", "9223372036854775808", "1e3", "1.2"])
    expect(
      correctionPreview.safeParse({
        ...preview,
        original: { ...preview.original, amount_minor },
      }).success
    ).toBe(false)
  expect(
    correctionPreview.safeParse({
      ...preview,
      original: { ...preview.original, amount_minor: "9223372036854775807" },
    }).success
  ).toBe(true)
})
it("invalidates the preview when the proposal changes", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(response(preview))
  mount()
  fireEvent.click(screen.getByRole("button", { name: "Preview correction" }))
  await screen.findByText(/Original TX-OLD/)
  fireEvent.change(screen.getByLabelText("Proposed amount (GBP)"), {
    target: { value: "3" },
  })
  expect(
    screen.getByRole("button", { name: "Record correction" })
  ).toBeDisabled()
  expect(screen.queryByText(/Original TX-OLD/)).toBeNull()
})
it.each([409, 500, 200])(
  "handles an unconfirmed write without retry (%s)",
  async (status) => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response(preview))
      .mockResolvedValueOnce(
        response(
          status === 200 ? { applied: true } : { detail: "Changed" },
          status
        )
      )
    mount()
    fireEvent.click(screen.getByRole("button", { name: "Preview correction" }))
    await screen.findByText(/Original TX-OLD/)
    fireEvent.click(screen.getByRole("button", { name: "Record correction" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      status === 409 ? "refused" : "may have been recorded"
    )
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(
      screen.queryByRole("button", { name: "Record correction" })
    ).toBeNull()
  }
)

it("previews source-field edits without requiring an amount change and resets the preview after another edit", async () => {
  const fields = {
    transaction_date: "2023-02-08",
    description: "Corrected description",
    running_balance_minor: "-125",
  }
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(
      response({
        ...preview,
        proposed: { ...preview.proposed, amount_minor: "100" },
        field_changes: fields,
      })
    )
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CorrectionForm
        caseId="case-a"
        transactionId="old"
        currency="GBP"
        initialRow={
          {
            key: "old",
            currency: "GBP",
            amount_minor: "100",
            running_balance_minor: null,
            transaction_date: "2023-02-07",
            description: "Original description",
          } as import("../api").LedgerTransaction
        }
        onClose={vi.fn()}
      />
    </QueryClientProvider>
  )
  expect(screen.getByLabelText("Proposed amount (GBP)")).toHaveValue("1.00")
  fireEvent.change(screen.getByLabelText("Transaction date"), {
    target: { value: "2023-02-08" },
  })
  fireEvent.change(screen.getByLabelText("Description"), {
    target: { value: "Corrected description" },
  })
  fireEvent.change(screen.getByLabelText("Running balance (GBP)"), {
    target: { value: "-1.25" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Preview correction" }))
  await screen.findByText("Changes to record")
  expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({
    amount_minor: "100",
    direction: "credit",
    fields,
  })
  fireEvent.change(screen.getByLabelText("Reason for correction"), {
    target: { value: "Checked original" },
  })
  expect(
    screen.getByRole("button", { name: "Record correction" })
  ).toBeEnabled()
  fireEvent.change(screen.getByLabelText("Transaction date"), {
    target: { value: "2023-02-09" },
  })
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Record correction" })
    ).toBeDisabled()
  )
})
