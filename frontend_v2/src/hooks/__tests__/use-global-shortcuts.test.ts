import { createElement } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { describe, it, expect, vi } from "vitest"
import { useAppStore } from "@/stores/app.store"
import { useGlobalShortcuts } from "../use-global-shortcuts"

function ShortcutHarness() {
  useGlobalShortcuts("case-1")
  const location = useLocation()
  return createElement("output", { "aria-label": "location" }, location.pathname)
}

describe("use-global-shortcuts", () => {
  it("Cmd+K toggles command palette via store", () => {
    useAppStore.setState({ commandPaletteOpen: false })
    useAppStore.getState().setCommandPaletteOpen(true)
    expect(useAppStore.getState().commandPaletteOpen).toBe(true)
  })

  it("keyboard event fires correctly", () => {
    const handler = vi.fn()
    document.addEventListener("keydown", handler)

    const event = new KeyboardEvent("keydown", { key: "k", ctrlKey: true })
    document.dispatchEvent(event)

    expect(handler).toHaveBeenCalledTimes(1)
    document.removeEventListener("keydown", handler)
  })

  it("opens Dossiers rather than the retired Profiles route with Ctrl+7", () => {
    render(
      createElement(
        MemoryRouter,
        { initialEntries: ["/cases/case-1/workspace"] },
        createElement(ShortcutHarness),
      ),
    )

    fireEvent.keyDown(document, { key: "7", ctrlKey: true })

    expect(screen.getByLabelText("location")).toHaveTextContent(
      "/cases/case-1/dossiers",
    )
  })
})
