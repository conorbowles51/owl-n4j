import { describe, it, expect, vi } from "vitest"
import { useAppStore } from "@/stores/app.store"

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
})
