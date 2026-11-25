import { fireEvent, render, screen, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AppSidebar } from "./sidebar"
import { preloadRouteIntent } from "@/lib/route-preload"

const shell = vi.hoisted(() => ({ expanded: true }))
vi.mock("@/stores/app.store", () => ({
  useAppStore: () => ({ sidebarExpanded: shell.expanded, toggleSidebar: vi.fn() }),
}))

// the Leads count (lx-leads B); every other call goes to the real client
vi.mock("@/lib/api-client", async (orig) => {
  const real = await orig<typeof import("@/lib/api-client")>()
  return { ...real, fetchAPI: (url: string, ...rest: unknown[]) =>
    url.endsWith("/leads/count") ? Promise.resolve({ count: 24, new: 3 }) : (real.fetchAPI as (...a: unknown[]) => unknown)(url, ...rest) }
})

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
  it("lx-corroredo E: Corroborate sits in the menu with the leads count only when the switch is on, and keeps the count when collapsed", async () => {
    const { setSwitch } = await import("@/lib/ui-switches")
    setSwitch("corroborate-v2", false)
    const off = sidebar()
    expect(screen.queryByRole("link", { name: /Corroborate/ })).toBeNull()
    off.unmount()
    setSwitch("corroborate-v2", true)
    const on = sidebar()
    expect(await within(await screen.findByRole("link", { name: /Corroborate/ })).findByText("24")).toBeInTheDocument()
    on.unmount()
    shell.expanded = false
    sidebar()
    expect(await screen.findByLabelText("24 leads")).toBeInTheDocument()
    shell.expanded = true
    setSwitch("corroborate-v2", false)
  })

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

  it("shows Phones in every case: one add entry with no phone, the full group once there is one (03 D-18)", async () => {
    phones.list = []
    const { unmount } = sidebar()
    await new Promise((r) => setTimeout(r, 0))
    const empty = screen.getByRole("region", { name: "Phones" })
    const add = within(empty).getAllByRole("link")
    expect(add.map((l) => l.textContent)).toEqual(["Phones — add a phone report"])
    expect(add[0]).toHaveAttribute("href", "/cases/case-1/phones")
    unmount()
    phones.list = [{ extraction_id: "e1", label: "C1" }]
    sidebar()
    // The phones query loads its API module on first use (lx-shell), so the group arrives after a module load: wait
    // for it with a cheap text query (a role query over the whole sidebar takes seconds on a loaded machine), then
    // check the group once.
    await screen.findByText("Phones", { selector: "span" }, { timeout: 15_000 })
    const group = screen.getByRole("region", { name: "Phones" })
    // one entry for every phone screen (phones redesign, screen 1): the six old entries and Help are gone
    expect(within(group).getAllByRole("link").map((l) => l.textContent?.replace(/Ctrl\+\d/, ""))).toEqual(["Phones"])
    expect(within(group).getByRole("link", { name: /Phones/ })).toHaveAttribute("href", "/cases/case-1/phones")
    expect(screen.queryByText("Phones (prototype)")).not.toBeInTheDocument()
  })
})

describe("AppSidebar Phones entry (phones redesign, screen 1)", () => {
  it("never carries a New mark, even inside the 7 days after a phone arrives", async () => {
    Object.assign(marks, { until: Date.now() + 60_000, hidden: false, saved: 0 })
    phones.list = [{ extraction_id: "e1", label: "Phone 1" }]
    sidebar()
    await screen.findByText("Phones", { selector: "span" }, { timeout: 15_000 })
    expect(screen.queryByText("New")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Hide the New marks" })).not.toBeInTheDocument()
  })
  it("is the current page on every phone screen", async () => {
    const { phonesEntryActive } = await import("./phones-entry")
    for (const p of ["/cases/c/phones", "/cases/c/phones/e1", "/cases/c/phones/e1/records/conversations", "/cases/c/conversations", "/cases/c/phone-analyses/plans", "/cases/c/phone-review", "/cases/c/phones/search"])
      expect(phonesEntryActive(p, "c")).toBe(true)
    for (const p of ["/cases/c/map", "/cases/c/phones-prototype/summary", "/cases/d/phones"]) expect(phonesEntryActive(p, "c")).toBe(false)
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
