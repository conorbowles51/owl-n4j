import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, fireEvent } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { CandidateFinalizationPanel } from "./CandidateFinalizationPanel"
vi.mock("./StatementDraftPanel", () => ({ StatementDraftPanel: () => null }))
const fixture = vi.hoisted(() => {
  const cell = {
    page_number: 1,
    table_index: 0,
    row_index: 0,
    column_index: 0,
    source_revision: "c".repeat(64),
    expected_text: "Printed dates",
  }
  return {
    scope: {
      account_id: "9445f4da-ed83-4819-9ce2-059cb259790a",
      currency: "GBP",
      candidate_ids: ["7b74f9db-9ff4-4325-a966-ddda8e957879"],
      start: { value: "2026-02-01", source: cell },
      end: { value: "2026-02-28", source: cell },
      opening: null,
      closing: null,
      balance_convention: "asset_balance",
      reason: "Reviewed dates",
    },
  }
})
vi.mock("./StatementScopeEditor", () => ({
  StatementScopeEditor: ({ onSave }: { onSave: (scope: unknown) => void }) => (
    <button onClick={() => onSave(fixture.scope)}>Save test statement</button>
  ),
}))
afterEach(() => vi.restoreAllMocks())
const ready = {
  case_id: "case",
  evidence_file_id: "file",
  applied: false,
  revision: "a".repeat(64),
  resolved_count: 1,
  rejected_count: 0,
  proof_class: "p3",
  included_in_default_totals: false,
  file_bytes_verified: true,
  source_sha256: "c".repeat(64),
  byte_count: 10,
  limitation: "Selected rows only",
  statement_scopes: [],
  readings: [
    {
      candidate_id: fixture.scope.candidate_ids[0],
      account_id: fixture.scope.account_id,
      currency: "GBP",
      account_label: "Test account",
      booking_date: "2026-02-01",
      transaction_date: null,
      description: "Test row",
    },
  ],
}
const receipt = {
  case_id: "case",
  evidence_file_id: "file",
  applied: true,
  created: true,
  finalization_id: "seal",
  finalization_revision: "b".repeat(64),
  source_document_id: "document",
  run_id: "run",
  transaction_count: 1,
  transactions: [
    {
      candidate_id: fixture.scope.candidate_ids[0],
      transaction_id: "transaction",
      ref_id: "TX-1",
      superseded_by_id: null,
    },
  ],
  proof_class_at_finalization: "p3",
  included_in_default_totals: false,
  limitation: "Selected rows only",
}
function mount(mismatch = false) {
  const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(
    async (url, options) =>
      new Response(
        JSON.stringify(
          String(url).includes("/finalize?")
            ? receipt
            : options?.method === "POST"
              ? {
                  ...ready,
                  revision: "b".repeat(64),
                  statement_scopes: [
                    {
                      ...fixture.scope,
                      reason: mismatch ? "Other reason" : fixture.scope.reason,
                    },
                  ],
                }
              : ready
        )
      )
  )
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <CandidateFinalizationPanel caseId="case" fileId="file" />
    </QueryClientProvider>
  )
  return fetch
}
async function add() {
  fireEvent.click(screen.getByRole("button", { name: "Preview finalization" }))
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Add printed statement controls",
    })
  )
  fireEvent.click(screen.getByRole("button", { name: "Save test statement" }))
  expect(
    screen.queryByRole("button", { name: "Finalize selected rows" })
  ).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Preview finalization" }))
}
it("requires a new bound preview and sends exactly those controls with finalization", async () => {
  const fetch = mount()
  await add()
  await screen.findByText(/1 resolved rows will become/)
  fireEvent.click(
    screen.getByRole("checkbox", { name: /These are documentary/ })
  )
  fireEvent.click(screen.getByRole("checkbox", { name: /I accept incomplete/ }))
  fireEvent.change(screen.getByLabelText("Reason for finalization"), {
    target: { value: "Reviewed scope" },
  })
  fireEvent.click(
    screen.getByRole("button", { name: "Finalize selected rows" })
  )
  expect(await screen.findByText(/Finalized 1 transactions/)).toBeVisible()
  const body = JSON.parse(String(fetch.mock.calls[2][1]?.body))
  expect(body).toMatchObject({
    expected_revision: "b".repeat(64),
    statement_scopes: [fixture.scope],
  })
})
it("refuses a preview that changed the submitted statement controls", async () => {
  mount(true)
  await add()
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "does not match the reviewed statement controls"
  )
  expect(
    screen.queryByRole("button", { name: "Finalize selected rows" })
  ).not.toBeInTheDocument()
})
