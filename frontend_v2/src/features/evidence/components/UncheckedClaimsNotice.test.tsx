import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { fetchAPI } from "@/lib/api-client"
import { UncheckedClaimsNotice } from "./UncheckedClaimsNotice"
import { uncheckedClaimsText } from "../utils/unchecked-claims"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const mocked = vi.mocked(fetchAPI)

function renderNotice(fileId: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <UncheckedClaimsNotice fileId={fileId} caseId="c1" />
    </QueryClientProvider>,
  )
}

describe("UncheckedClaimsNotice", () => {
  beforeEach(() => {
    mocked.mockReset()
    mocked.mockImplementation(async (endpoint: string) =>
      endpoint.endsWith("/check")
        ? { queued: true, message: "Checking started" }
        : { case_id: "c1", unchecked: 1250, files: [{ evidence_file_id: "f1", filename: "a.pdf", unchecked: 250 }] },
    )
  })

  it("says how many of the file's claims were not checked and starts the check", async () => {
    renderNotice("f1")
    expect(await screen.findByText(uncheckedClaimsText(250))).toBeTruthy()
    expect(screen.getByText(/1,250 unchecked claims in all/)).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Check them" }))
    await waitFor(() => expect(mocked).toHaveBeenCalledWith("/api/claim-checks/c1/check", { method: "POST" }))
  })

  it("says nothing for a file whose claims were all checked", async () => {
    const { container } = renderNotice("other")
    await waitFor(() => expect(mocked).toHaveBeenCalled())
    expect(container.textContent).toBe("")
  })
})
