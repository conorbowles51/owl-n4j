// This existing workflow fixture has case editing and upload access.
vi.mock("../hooks/use-financial-access", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../hooks/use-financial-access")>()),
  useFinancialAccess: () => ({
    canEdit: true,
    canUpload: true,
    ready: true,
    error: false,
  }),
}))
import { render, screen, fireEvent } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { savedIndirectFixture } from "@/test/indirect-workpaper-fixture"
import { verifyIndirectReview } from "../lib/indirect-review"
import { useFinancialDraftStore } from "../stores/financial-drafts"
import { IndirectReviewWorkbench } from "./IndirectReviewWorkbench"
const api = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI: api }))
beforeEach(() => {
  api.mockReset()
  useFinancialDraftStore.setState({ drafts: {} })
})
it("restores a revised workpaper's inputs separately from another copy", async () => {
  const f = await savedIndirectFixture()
  const initial = await verifyIndirectReview(f.envelope, f.catalog, f.inputs)
  api.mockResolvedValue(f.catalog)
  const mount = (source = "original-note") =>
    render(
      <QueryClientProvider client={new QueryClient()}>
        <IndirectReviewWorkbench
          caseId={f.caseId}
          initialReview={initial}
          copiedFrom={source}
        />
      </QueryClientProvider>
    )
  const first = mount()
  await screen.findByLabelText("Indirect amount uses")
  fireEvent.change(screen.getByLabelText("Indirect amount uses"), {
    target: { value: "777.00" },
  })
  fireEvent.change(screen.getByLabelText("Amount basis uses"), {
    target: { value: "Checked the revised evidence" },
  })
  first.unmount()
  const next = mount()
  expect(await screen.findByLabelText("Indirect amount uses")).toHaveValue(
    "777.00"
  )
  expect(screen.getByLabelText("Amount basis uses")).toHaveValue(
    "Checked the revised evidence"
  )
  expect(
    screen.queryByRole("region", { name: "Indirect workpaper result" })
  ).not.toBeInTheDocument()
  next.unmount()
  mount("another-note")
  expect(await screen.findByLabelText("Indirect amount uses")).not.toHaveValue(
    "777.00"
  )
})
