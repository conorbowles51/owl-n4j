import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import { ApiError, fetchAPI } from "@/lib/api-client"
import { KeepDuplicateCopy } from "./KeepDuplicateCopy"

vi.mock("@/lib/api-client", async (original) => ({
  ...(await original<typeof import("@/lib/api-client")>()),
  fetchAPI: vi.fn(),
}))

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

const caseId = "10000000-0000-4000-8000-000000000001"
const sourceId = "10000000-0000-4000-8000-000000000002"

function renderForm() {
  const client = new QueryClient()
  render(
    <QueryClientProvider client={client}>
      <KeepDuplicateCopy caseId={caseId} sourceDocumentId={sourceId} />
    </QueryClientProvider>
  )
}

it("needs a reason and posts it for this copy", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ applied: true })
  renderForm()
  const button = screen.getByRole("button", { name: "Keep this copy instead" })
  expect(button).toBeDisabled()
  fireEvent.change(screen.getByLabelText("Why this copy should count instead"), {
    target: { value: "  Cited production  " },
  })
  fireEvent.click(button)
  await waitFor(() => expect(screen.getByRole("status")).toBeTruthy())
  expect(fetchAPI).toHaveBeenCalledWith(
    `/api/financial/documents/${sourceId}/keep-duplicate-copy?case_id=${caseId}`,
    { method: "POST", body: { reason: "Cited production" } }
  )
  expect(button).toBeDisabled()
})

it("says nothing changed when the decision is refused", async () => {
  vi.mocked(fetchAPI).mockRejectedValue(
    new ApiError("The payments or printed balances were read differently.", 409)
  )
  renderForm()
  fireEvent.change(screen.getByLabelText("Why this copy should count instead"), {
    target: { value: "Cited production" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Keep this copy instead" }))
  await waitFor(() =>
    expect(screen.getByRole("alert").textContent).toContain("Nothing changed")
  )
})
