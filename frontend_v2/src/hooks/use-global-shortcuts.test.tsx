import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { useGlobalShortcuts } from "./use-global-shortcuts"
import { useUnsavedHistoryGuard } from "./use-unsaved-history-guard"

function Draft() {
  useGlobalShortcuts("case-1")
  useUnsavedHistoryGuard(true)
  return <output>{useLocation().pathname}</output>
}
describe("Shell shortcuts with unsaved work", () => {
  it("keeps a dirty editor on cancel and navigates only after discard is accepted", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false)
    render(
      <MemoryRouter initialEntries={["/cases/case-1/workspace"]}>
        <Draft />
      </MemoryRouter>
    )
    fireEvent.keyDown(document, { key: "1", ctrlKey: true })
    expect(screen.getByRole("status")).toHaveTextContent(
      "/cases/case-1/workspace"
    )
    expect(confirm).toHaveBeenCalledOnce()
    confirm.mockReturnValue(true)
    fireEvent.keyDown(document, { key: "1", ctrlKey: true })
    expect(screen.getByRole("status")).toHaveTextContent("/cases/case-1/graph")
    confirm.mockRestore()
  })
})
