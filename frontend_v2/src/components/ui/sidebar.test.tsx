import { render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AppSidebar } from "./sidebar"

vi.mock("@/stores/app.store", () => ({
  useAppStore: () => ({ sidebarExpanded: true, toggleSidebar: vi.fn() }),
}))

vi.mock("@/features/auth/hooks/use-auth", () => ({
  useAuthStore: () => ({ user: { global_role: "user" } }),
}))

vi.mock("@/features/significant/components/CaseLayerSwitcher", () => ({
  CaseLayerSwitcher: () => <div>Layers</div>,
}))

vi.mock("@/hooks/use-media-query", () => ({ useMediaQuery: () => false }))

describe("AppSidebar case navigation", () => {
  it("places Workspace, Dossiers, and Reports above case views and removes case Profiles", () => {
    render(
      <MemoryRouter initialEntries={["/cases/case-1/workspace"]}>
        <TooltipProvider>
          <Routes>
            <Route path="/cases/:id/*" element={<AppSidebar />} />
          </Routes>
        </TooltipProvider>
      </MemoryRouter>,
    )

    const workspace = screen.getByRole("region", { name: "Workspace" })
    expect(within(workspace).getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Workspace",
      "Dossiers",
      "Reports",
    ])

    const caseViews = screen.getByRole("region", { name: "Case views" })
    expect(workspace.compareDocumentPosition(caseViews) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    const fullData = screen.getByRole("region", { name: "Full case data" })
    expect(within(fullData).queryByText("Profiles")).not.toBeInTheDocument()
  })
})
