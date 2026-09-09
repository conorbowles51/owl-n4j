import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, useLocation } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { WorkspaceRedesignPage } from "./WorkspaceRedesignPage"

vi.mock("@/features/cases/hooks/use-cases", () => ({
  useCase: () => ({ data: { id: "case-1" } }),
}))

vi.mock("@/features/cases/hooks/use-case-permissions", () => ({
  useCasePermissions: () => ({ canEdit: true }),
}))

vi.mock("./CanonicalWorkspaceOverview", () => ({
  CanonicalWorkspaceOverview: ({ onOpenCasework }: { onOpenCasework: () => void }) => (
    <div>Overview content <button onClick={onOpenCasework}>Open recent casework</button></div>
  ),
}))

vi.mock("./CaseworkListView", () => ({
  CaseworkListView: ({
    entryType,
    initialSelectedEntryId,
  }: {
    entryType: string
    initialSelectedEntryId?: string | null
  }) => <div>{entryType} list {initialSelectedEntryId ?? "no selection"}</div>,
}))

vi.mock("./TasksSection", () => ({
  TasksSection: ({ initialItemId }: { initialItemId?: string | null }) => (
    <div>Work content {initialItemId ?? "no target"}</div>
  ),
}))

function LocationProbe() {
  const location = useLocation()
  return <output aria-label="location">{location.pathname}{location.search}</output>
}

function renderPage(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <WorkspaceRedesignPage caseId="case-1" />
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe("WorkspaceRedesignPage", () => {
  it("opens notebook notes in Casework", () => {
    renderPage("/cases/case-1/workspace?view=casework&kind=note&entry=note-1")
    expect(screen.getByRole("tab", { name: "Notes" })).toHaveAttribute("data-state", "active")
    expect(screen.getByText("note list note-1")).toBeVisible()
  })
  it("opens a stable Work deep link and preserves its target", () => {
    renderPage("/cases/case-1/workspace?view=work&item=task-1")
    expect(screen.getByText("Work content task-1")).toBeInTheDocument()
    expect(screen.getByLabelText("location")).toHaveTextContent("?view=work&item=task-1")
  })

  it("opens a targeted theory from an overview deep link", () => {
    renderPage(
      "/cases/case-1/workspace?view=casework&kind=theory&entry=theory-1",
    )
    expect(screen.getByRole("tab", { name: /theories/i })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(screen.getByText("theory list theory-1")).toBeInTheDocument()
  })

  it("writes tab changes to the URL and clears stale item targets", async () => {
    const user = userEvent.setup()
    renderPage("/cases/case-1/workspace?view=work&item=task-1")
    await user.click(screen.getByRole("tab", { name: /casework/i }))
    await waitFor(() =>
      expect(screen.getByLabelText("location")).toHaveTextContent("?view=casework"),
    )
    expect(screen.getByLabelText("location")).not.toHaveTextContent("item=")

    await user.click(screen.getByRole("tab", { name: /overview/i }))
    await waitFor(() =>
      expect(screen.getByLabelText("location")).toHaveTextContent("/cases/case-1/workspace"),
    )
    expect(screen.getByLabelText("location")).not.toHaveTextContent("?")
  })

  it("lets overview links open the canonical Casework view", () => {
    renderPage("/cases/case-1/workspace")
    fireEvent.click(screen.getByRole("button", { name: "Open recent casework" }))
    expect(screen.getByLabelText("location")).toHaveTextContent("?view=casework")
  })
})
