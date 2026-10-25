import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const fetchAPI = vi.fn()
vi.mock("@/lib/api-client", () => ({
  fetchAPI: (...args: unknown[]) => fetchAPI(...args),
}))

import { ReaderReplacementNotice } from "./ReaderReplacementNotice"

const notice = {
  status: "replaced" as const,
  message:
    "Loupe replaced this saved statement with a reading that balances; your earlier version is kept (Restore).",
  counting_source_document_id: "new-doc",
  replacement_source_document_id: "new-doc",
  replaced_source_document_id: "old-doc",
  investigator_work: true,
  can_restore: true,
}

function renderNotice(canEdit = true) {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <ReaderReplacementNotice
        caseId="case-1"
        notice={notice}
        canEdit={canEdit}
      />
    </QueryClientProvider>
  )
}

describe("ReaderReplacementNotice", () => {
  beforeEach(() => fetchAPI.mockReset())

  it("tells the investigator the saved statement was replaced and restores on request", async () => {
    fetchAPI.mockResolvedValue({ applied: true })
    renderNotice()
    expect(screen.getByText(notice.message)).toBeTruthy()
    fireEvent.click(
      screen.getByRole("button", { name: "Restore earlier version" })
    )
    await waitFor(() => expect(fetchAPI).toHaveBeenCalledTimes(1))
    expect(fetchAPI.mock.calls[0][0]).toBe(
      "/api/financial/documents/new-doc/restore-replaced-statement?case_id=case-1"
    )
  })

  it("offers no restore to a reader without edit access", () => {
    renderNotice(false)
    expect(screen.queryByRole("button")).toBeNull()
  })
})
