import { fireEvent, render, screen, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AppSidebar } from "./sidebar"
import { preloadRouteIntent } from "@/lib/route-preload"

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
// The sidebar's phones query (shared with the Phones page and the start-up prefetch) answers from this list.
vi.mock("@/features/phones/phones-query", () => ({
  phonesQuery: (caseId: string) => ({
    queryKey: ["phones", caseId],
    queryFn: async () => ({ case_id: caseId, phones: phones.list }),
  }),
}))

vi.mock("@/lib/route-preload", () => ({ preloadRouteIntent: vi.fn(() => true) }))

const marks = vi.hoisted(() => ({ until: 0, hidden: false, saved: 0 }))
vi.mock("@/features/phones/marks", () => ({
  HELP_PARAM: "help",
  marksQuery: { queryKey: ["marks"], queryFn: async () => ({ marks: marks.hidden ? { phones_new_hidden: "t" } : {} }) },
  newMarksUntil: () => marks.until,
  hideNewMarks: async () => {
    marks.saved += 1
    return { marks: { phones_new_hidden: "t" } }
  },
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
    // The phones query loads its API module on first use (lx-shell), so the group arrives after a module load: wait
    // for it with a cheap text query (a role query over the whole sidebar takes seconds on a loaded machine), then
    // check the group once.
    await screen.findByText("Phone summary", undefined, { timeout: 15_000 })
    const group = screen.getByRole("region", { name: "Phones" })
    expect(within(group).getAllByRole("link").map((l) => l.textContent?.replace(/Ctrl\+\d/, ""))).toEqual([
      "Phone summary", "Conversations", "Patterns", "Money on the phones", "Analyses", "Needs a decision", "Help",
    ])
    expect(within(group).getByRole("link", { name: /Conversations/ })).toHaveAttribute("href", "/cases/case-1/conversations")
    expect(screen.queryByText("Phones (prototype)")).not.toBeInTheDocument()
  })
})

describe("AppSidebar New marks (07 section 9)", () => {
  const withPhone = () => {
    phones.list = [{ extraction_id: "e1", label: "Phone 1" }]
    sidebar()
  }
  it("marks the phone items inside the 7 days, and hiding them is saved", async () => {
    Object.assign(marks, { until: Date.now() + 60_000, hidden: false, saved: 0 })
    withPhone()
    const hide = await screen.findByRole("button", { name: "Hide the New marks" }, { timeout: 15_000 })
    expect(screen.getAllByText("New")).toHaveLength(6)
    fireEvent.click(hide)
    await vi.waitFor(() => expect(screen.queryByText("New")).not.toBeInTheDocument())
    expect(marks.saved).toBe(1)
  })
  it("shows no mark once the 7 days have passed, or once this person hid them", async () => {
    Object.assign(marks, { until: Date.now() - 1, hidden: false })
    withPhone()
    await screen.findByText("Phone summary", undefined, { timeout: 15_000 })
    expect(screen.queryByText("New")).not.toBeInTheDocument()
  })
  it("reopens the first-phone card from Help", async () => {
    Object.assign(marks, { until: 0 })
    withPhone()
    expect(await screen.findByRole("link", { name: /Help/ }, { timeout: 15_000 })).toHaveAttribute("href", "/cases/case-1/phones?help=phones")
  })
})

describe("AppSidebar navigation intent", () => {
  it("pointing at or focusing a case view link starts that page's code (not on render)", () => {
    vi.mocked(preloadRouteIntent).mockClear()
    sidebar()
    expect(preloadRouteIntent).not.toHaveBeenCalled()
    const caseViews = screen.getByRole("region", { name: "Case views" })
    const [first, second] = within(caseViews).getAllByRole("link")
    fireEvent.pointerEnter(first)
    expect(preloadRouteIntent).toHaveBeenLastCalledWith(first.getAttribute("href"))
    fireEvent.focus(second)
    expect(preloadRouteIntent).toHaveBeenLastCalledWith(second.getAttribute("href"))
    expect(preloadRouteIntent).toHaveBeenCalledTimes(2)
  })
})
