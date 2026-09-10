import { useState } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"
import { CaseLayout } from "./CaseLayout"
vi.mock("@/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  ResizablePanel: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  ResizableHandle: () => <div />,
}))
const state = vi.hoisted(() => ({ narrow: false, collapsed: true }))
vi.mock("@/hooks/use-media-query", () => ({
  useMediaQuery: () => state.narrow,
}))
vi.mock("@/stores/ui.store", () => ({
  useUIStore: (select: (s: unknown) => unknown) =>
    select({ graphPanelCollapsed: state.collapsed }),
}))
vi.mock("react-router-dom", () => ({
  useParams: () => ({ id: "case" }),
  useMatch: () => null,
  Outlet: () => {
    const [value, setValue] = useState("")
    return (
      <input
        aria-label="Unfinished case work"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
    )
  },
}))
vi.mock("@/components/ui/error-boundary", () => ({
  ErrorBoundary: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}))
vi.mock("./CaseSidePanel", () => ({
  CaseSidePanelRail: () => <div>Panel rail</div>,
  CaseSidePanelContent: () => <div>Panel content</div>,
}))
vi.mock("@/features/evidence/components/EvidenceContextSidebar", () => ({
  EvidenceContextSidebar: () => null,
}))
it("preserves unfinished page state when resizing and toggling the case side panel", () => {
  state.narrow = false
  state.collapsed = true
  const view = render(<CaseLayout />)
  const input = screen.getByLabelText("Unfinished case work")
  fireEvent.change(input, { target: { value: "Unsubmitted review" } })
  for (const [narrow, collapsed] of [
    [true, true],
    [true, false],
    [false, false],
    [false, true],
  ]) {
    state.narrow = narrow
    state.collapsed = collapsed
    view.rerender(<CaseLayout />)
    expect(screen.getByLabelText("Unfinished case work")).toBe(input)
    expect(input).toHaveValue("Unsubmitted review")
  }
})
