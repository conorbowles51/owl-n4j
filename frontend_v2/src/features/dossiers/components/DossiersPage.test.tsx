import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { DossiersPage } from "./DossiersPage"

vi.mock("@/features/cases/hooks/use-cases", () => ({
  useCase: () => ({ data: { id: "case-1" } }),
}))

vi.mock("@/features/cases/hooks/use-case-permissions", () => ({
  useCasePermissions: () => ({ canEdit: true }),
}))

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock("../hooks", () => ({
  useDossiers: () => ({
    data: {
      dossiers: [
        {
          id: "dossier-1",
          case_id: "case-1",
          dossier_type: "person",
          display_name: "Henry Example",
          display_name_snapshot: "Henry Example",
          linkage_state: "linked",
          status: "active",
          needs_link_review: false,
          graph_entity_deleted: false,
          roles: [],
        },
      ],
      total: 1,
      limit: 100,
      offset: 0,
    },
    isLoading: false,
  }),
}))

vi.mock("./DossierCreateSheet", () => ({
  DossierCreateSheet: () => null,
}))

vi.mock("./DossierDetailSheet", () => ({
  DossierDetailSheet: ({
    dossierId,
    open,
    onOpenChange,
  }: {
    dossierId: string | null
    open: boolean
    onOpenChange: (value: boolean) => void
  }) =>
    open ? (
      <div>
        <span>Open Dossier {dossierId}</span>
        <button type="button" onClick={() => onOpenChange(false)}>Close Dossier</button>
      </div>
    ) : null,
}))

function LocationProbe() {
  const location = useLocation()
  return <output aria-label="location">{location.pathname}{location.search}</output>
}

function renderPage(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/cases/:id/dossiers" element={<DossiersPage />} />
      </Routes>
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe("DossiersPage deep links", () => {
  it("opens a linked Dossier and keeps selection in the URL", () => {
    renderPage("/cases/case-1/dossiers?dossier=dossier-1")
    expect(screen.getByText("Open Dossier dossier-1")).toBeInTheDocument()
    expect(screen.getByLabelText("location")).toHaveTextContent(
      "?dossier=dossier-1",
    )
  })

  it("updates and clears the Dossier selection without losing other parameters", async () => {
    const user = userEvent.setup()
    renderPage("/cases/case-1/dossiers?source=workspace")

    await user.click(screen.getByRole("button", { name: /henry example/i }))
    expect(screen.getByLabelText("location")).toHaveTextContent(
      "?source=workspace&dossier=dossier-1",
    )

    await user.click(screen.getByRole("button", { name: "Close Dossier" }))
    expect(screen.getByLabelText("location")).toHaveTextContent(
      "/cases/case-1/dossiers?source=workspace",
    )
  })
})
