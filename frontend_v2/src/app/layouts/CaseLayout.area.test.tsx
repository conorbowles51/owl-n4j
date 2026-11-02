// lx-style C: every case route renders its area identity through the one shared ViewHeader.
import { readFileSync } from "node:fs"
import path from "node:path"
import { render, screen, cleanup } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import { CaseLayout } from "./CaseLayout"
import { AREAS, CASE_VIEWS } from "@/lib/areas"
import { EmptyState } from "@/components/ui/empty-state"

vi.mock("@/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizablePanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizableHandle: () => <div />,
}))
vi.mock("@/hooks/use-media-query", () => ({ useMediaQuery: () => false }))
vi.mock("@/stores/ui.store", () => ({
  useUIStore: (select: (s: unknown) => unknown) => select({ graphPanelCollapsed: true }),
}))
vi.mock("./CaseSidePanel", () => ({
  CaseSidePanelRail: () => <div />,
  CaseSidePanelContent: () => <div />,
}))
vi.mock("@/features/evidence/components/EvidenceContextSidebar", () => ({ EvidenceContextSidebar: () => null }))

afterEach(cleanup)

/** The child routes of /cases/:id in routes.tsx, read from the source so a new route cannot skip its area. */
function caseRouteSegments(): string[] {
  const src = readFileSync(path.resolve(__dirname, "../routes.tsx"), "utf8")
  const start = src.indexOf('<Route path="/cases/:id"')
  const end = src.indexOf("</Route>", start)
  return [...src.slice(start, end).matchAll(/<Route path="([^"/:]+)/g)].map((m) => m[1])
}

function renderAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/cases/:id" element={<CaseLayout />}>
          <Route path="*" element={<EmptyState title="Nothing here yet" icon={() => <svg data-testid="icon" />} />} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

describe("case view area identity", () => {
  it("every case route in routes.tsx has an area", () => {
    const segments = caseRouteSegments()
    expect(segments.length).toBeGreaterThanOrEqual(15)
    for (const s of segments) expect(CASE_VIEWS.some((v) => v.segment === s), `route ${s} has no area`).toBe(true)
  })

  for (const view of CASE_VIEWS) {
    it(`/cases/:id/${view.segment} shows the ${view.area} band, its title and tints its empty state`, () => {
      renderAt(`/cases/c1/${view.segment}`)
      const header = screen.getByTestId("view-header")
      expect(header).toHaveAttribute("data-area", view.area)
      expect(header.className).toContain(`bg-area-${view.area}-soft`)
      expect(header).toHaveTextContent(view.title)
      expect(header).toHaveTextContent(AREAS[view.area].label)
      expect(document.title).toBe(`${view.title} · Loupe`)
      const tile = screen.getByTestId("icon").parentElement!
      expect(tile).toHaveAttribute("data-area", view.area)
      expect(tile.className).toContain(`bg-area-${view.area}-soft`)
    })
  }

  it("views in different areas never share a band colour", () => {
    const byArea = new Map<string, string>()
    for (const view of CASE_VIEWS) {
      renderAt(`/cases/c1/${view.segment}`)
      const cls = [...screen.getByTestId("view-header").classList].find((c) => c.startsWith("bg-area-"))!
      if (byArea.has(view.area)) expect(cls).toBe(byArea.get(view.area))
      for (const [area, other] of byArea) if (area !== view.area) expect(cls).not.toBe(other)
      byArea.set(view.area, cls)
      cleanup()
    }
    expect(byArea.size).toBe(8)
  })
})
