import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { InvestigatorFindingEditor } from "./InvestigatorFindingEditor"

vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({ canEdit: true, canUpload: true, ready: true, error: false }),
}))
vi.mock("@/features/workspace/hooks/use-casework", () => ({
  useCreateCaseworkEntry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateCaseworkEntry: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
afterEach(cleanup)

it("shows record type, progress, next action and assignee without unfolding anything", () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <InvestigatorFindingEditor caseId="case" ids={["t1"]} onClose={vi.fn()} />
    </QueryClientProvider>
  )
  expect(screen.getByRole("group", { name: "Follow-up and record details (optional)" })).toBeVisible()
  for (const name of ["Record type", "Progress", "Next action"]) expect(screen.getByLabelText(name)).toBeVisible()
  expect(screen.getByRole("option", { name: "Conclusion" })).toBeTruthy()
})
