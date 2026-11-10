import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { expect, it, vi } from "vitest"
import type { CaseworkEntry } from "../casework-api"
import { CaseworkDetailSheet } from "./CaseworkDetailSheet"

const TXN = "2d8e4c3a-9f6b-4e3c-9a4d-7b5c0e1f2a33"
const entry: CaseworkEntry = {
  id: "finding-1", case_id: "case-1", entry_type: "finding", title: "Paid the day after the message",
  body: "Bundle", tags: [], review_state: "accepted", version: 1, migration_metadata: {},
  needs_migration_review: false, revisions: [], events: [],
  actor_origin: { kind: "model", model: "DeepSeek V4 Pro", model_id: "deepseek-v4-pro" },
  origin_label: "Drafted by DeepSeek V4 Pro, accepted by Investigator",
  links: [{
    id: "l1", target_type: "financial_transaction", target_id: TXN, target_label: "2024-03-02 · debit 1,234.56 USD · Wire to ACME",
    relationship: "supports", source_anchor: { cite: `txn://${TXN}` },
  } as never],
}
vi.mock("../hooks/use-casework", () => {
  const mutation = () => ({ mutateAsync: vi.fn(), isPending: false })
  return {
    useCaseworkEntry: () => ({ data: entry, isLoading: false }),
    useChangeCaseworkLifecycle: mutation, useConvertTheory: mutation, useDeleteCaseworkEntry: mutation,
    useRestoreCaseworkEntry: mutation, useCreateCaseworkEntry: mutation, useUpdateCaseworkEntry: mutation,
    useChangeCaseworkConfidence: mutation, useChangeCaseworkSignificance: mutation,
    useAttachmentOptions: () => ({ data: { items: [] }, isLoading: false }),
  }
})
vi.mock("../hooks/use-current-casework-links", () => ({ useCurrentCaseworkLinks: () => [] }))
vi.mock("@/features/workspace-ai/components/WorkspaceAIPanel", () => ({ WorkspaceAIPanel: () => null }))

function Where() {
  const location = useLocation()
  return <p data-testid="where">{location.pathname + location.search}</p>
}

it("shows who drafted and accepted an entry, and opens its payment on the Financial page", () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/cases/case-1/workspace"]}>
        <Routes>
          <Route path="*" element={<><CaseworkDetailSheet caseId="case-1" entryId="finding-1" open canEdit onOpenChange={vi.fn()} /><Where /></>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  expect(screen.getByTestId("entry-origin")).toHaveTextContent("Drafted by DeepSeek V4 Pro, accepted by Investigator")
  const payment = screen.getAllByRole("button", { name: /Wire to ACME/ })[0]
  expect(payment).toBeEnabled()
  fireEvent.click(payment)
  expect(screen.getByTestId("where")).toHaveTextContent(`/cases/case-1/financial?view=transactions&payment=${TXN}`)
})

it("keeps the underlying work open when its draft blocks navigation from linked material", () => {
  const onBeforeNavigate = vi.fn().mockReturnValue(false)
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={["/cases/case-1/workspace?view=work"]}><CaseworkDetailSheet caseId="case-1" entryId="finding-1" open canEdit onOpenChange={vi.fn()} onBeforeNavigate={onBeforeNavigate} /><Where /></MemoryRouter></QueryClientProvider>)
  fireEvent.click(screen.getByRole("button", { name: /Wire to ACME/ }))
  expect(onBeforeNavigate).toHaveBeenCalledOnce()
  expect(screen.getByTestId("where")).toHaveTextContent("/cases/case-1/workspace?view=work")
  onBeforeNavigate.mockReturnValue(true)
  fireEvent.click(screen.getByRole("button", { name: /Wire to ACME/ }))
  expect(screen.getByTestId("where")).toHaveTextContent(`/cases/case-1/financial?view=transactions&payment=${TXN}`)
})
