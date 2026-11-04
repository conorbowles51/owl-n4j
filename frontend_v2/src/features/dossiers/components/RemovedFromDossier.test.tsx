import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, expect, it, vi } from "vitest"
import { fetchAPI } from "@/lib/api-client"
import { RemovedFromDossier } from "./RemovedFromDossier"

vi.mock("@/lib/api-client", () => ({ fetchAPI: vi.fn() }))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const item = {
  id: "r1",
  kind: "dossier_interview",
  subject_id: "i1",
  label: "Interview 2025-07",
  removed_by: "alex@example.test",
  removed_at: "2026-11-04T01:00:00Z",
  dossier_id: "d1",
}

function mount(canEdit = true) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <RemovedFromDossier caseId="c1" dossierId="d1" canEdit={canEdit} />
    </QueryClientProvider>
  )
}

beforeEach(() => vi.resetAllMocks())

// followups m11032229063349: a removed interview (with its working notes) could not be put back.
it("lists what was removed from the dossier and puts it back", async () => {
  let restored = false
  vi.mocked(fetchAPI).mockImplementation(async (_url, options) => {
    if (options?.method === "POST") {
      restored = true
      return { ...item, restored_at: "2026-11-04T01:05:00Z" } as never
    }
    return { items: restored ? [] : [item] } as never
  })
  mount()
  expect(await screen.findByText("Removed from this dossier (1)")).toBeInTheDocument()
  expect(screen.getByText(/Interview 2025-07/)).toBeInTheDocument()
  expect(screen.getByText(/by alex@example.test/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole("button", { name: "Put back" }))
  await waitFor(() =>
    expect(fetchAPI).toHaveBeenCalledWith(
      "/api/cases/c1/removed-records/r1/restore",
      { method: "POST" }
    )
  )
  expect(fetchAPI).toHaveBeenCalledWith("/api/cases/c1/removed-records?dossier_id=d1")
  await waitFor(() => expect(screen.queryByText(/Removed from this dossier/)).toBeNull())
})

it("shows nothing when nothing was removed, and no Put back without edit access", async () => {
  vi.mocked(fetchAPI).mockResolvedValue({ items: [] } as never)
  const { container } = mount()
  await waitFor(() => expect(fetchAPI).toHaveBeenCalled())
  expect(container).toBeEmptyDOMElement()
  vi.mocked(fetchAPI).mockResolvedValue({ items: [item] } as never)
  mount(false)
  expect(await screen.findByText("Removed from this dossier (1)")).toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "Put back" })).toBeNull()
})
