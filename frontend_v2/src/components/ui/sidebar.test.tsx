import { fireEvent, render, screen, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
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

const phones = vi.hoisted(() => ({ list: [] as { extraction_id: string; label: string }[] }))
vi.mock("@/features/phones/api", () => ({
  getPhones: async (caseId: string) => ({ case_id: caseId, phones: phones.list }),
}))

function sidebar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/cases/case-1/workspace"]}>
        <TooltipProvider>
          <Routes>
            <Route path="/cases/:id/*" element={<AppSidebar />} />
          </Routes>
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("AppSidebar case navigation", () => {
  it("places Workspace, Dossiers, and Reports above case views and removes case Profiles", () => {
    sidebar()

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

  it("offers Search this case, which opens the same search as Ctrl+K (03 section 11.4)", () => {
    sidebar()
    const heard = vi.fn()
    document.addEventListener("owl:toggle-command-palette", heard)
    fireEvent.click(screen.getByRole("button", { name: /Search this case/ }))
    document.removeEventListener("owl:toggle-command-palette", heard)
    expect(heard).toHaveBeenCalledTimes(1)
  })

  it("shows the Phones group only when the case has a phone (03 D-18)", async () => {
    phones.list = []
    const { unmount } = sidebar()
    await new Promise((r) => setTimeout(r, 0))
    expect(screen.queryByRole("region", { name: "Phones" })).not.toBeInTheDocument()
    unmount()
    phones.list = [{ extraction_id: "e1", label: "C1" }]
    sidebar()
    const group = await screen.findByRole("region", { name: "Phones" })
    expect(within(group).getAllByRole("link").map((l) => l.textContent?.replace(/Ctrl\+\d/, ""))).toEqual([
      "Phone summary", "Conversations", "Patterns", "Needs a decision",
    ])
    expect(within(group).getByRole("link", { name: /Conversations/ })).toHaveAttribute("href", "/cases/case-1/conversations")
    expect(screen.queryByText("Phones (prototype)")).not.toBeInTheDocument()
  })
})
