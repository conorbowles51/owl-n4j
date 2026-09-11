import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { savedIndirectFixture } from "@/test/indirect-workpaper-fixture"
import { SavedIndirectFinding } from "./SavedIndirectFinding"
const api = vi.hoisted(() => vi.fn())
vi.mock("@/lib/api-client", () => ({ fetchAPI: api }))
vi.mock("@/components/ui/document-viewer", () => ({
  DocumentViewer: ({ documentName }: { documentName: string }) => (
    <div>Viewing original {documentName}</div>
  ),
}))
vi.mock("./IndirectReviewWorkbench", () => ({
  IndirectReviewWorkbench: ({
    copiedFrom,
    initialReview,
  }: {
    copiedFrom: string
    initialReview: { value: { inputs: { subject: string } } }
  }) => (
    <div>
      New copy of {copiedFrom}: {initialReview.value.inputs.subject}
      <input aria-label="Working copy note" />
    </div>
  ),
}))
beforeEach(() => api.mockReset())
async function setup() {
  const f = await savedIndirectFixture()
  api.mockResolvedValue(f.catalog)
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <SavedIndirectFinding caseId={f.caseId} entry={f.entry} link={f.link} />
    </QueryClientProvider>
  )
  fireEvent.click(screen.getByRole("button", { name: "Open saved workpaper" }))
  await screen.findByText("Calculated difference: 40.00 GBP")
  return f
}
it("shows saved amounts, checks and source before preparing a separate retained copy", async () => {
  await setup()
  expect(screen.getByText("100.00 GBP")).toBeTruthy()
  expect(screen.getByText("60.00 GBP")).toBeTruthy()
  expect(screen.getByText("Opening cash checked: Marked reviewed")).toBeTruthy()
  expect(api).not.toHaveBeenCalled()
  fireEvent.click(
    screen.getAllByRole("button", { name: "Open source: Synthetic.pdf" })[0]
  )
  expect(screen.getByText("Viewing original Synthetic.pdf")).toBeTruthy()
  fireEvent.click(screen.getByRole("button", { name: "Create revised copy" }))
  await screen.findByText("New copy of saved-note: Synthetic saved workpaper")
  expect(api).toHaveBeenCalledWith(
    expect.stringContaining("indirect-review-methods?case_id=")
  )
  fireEvent.change(screen.getByLabelText("Working copy note"), {
    target: { value: "Keep this change" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Hide revised copy" }))
  fireEvent.click(screen.getByRole("button", { name: "Continue revised copy" }))
  expect(screen.getByLabelText("Working copy note")).toHaveValue(
    "Keep this change"
  )
})
it("retains readable saved results when current definitions cannot prepare a copy", async () => {
  await setup()
  api.mockRejectedValueOnce(Error("Methods unavailable"))
  fireEvent.click(screen.getByRole("button", { name: "Create revised copy" }))
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Methods unavailable"
  )
  expect(screen.getByText("Calculated difference: 40.00 GBP")).toBeTruthy()
  expect(screen.queryByLabelText("Working copy note")).toBeNull()
})
