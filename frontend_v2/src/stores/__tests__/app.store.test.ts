import { describe, it, expect, beforeEach } from "vitest"
import { useAppStore } from "../app.store"

describe("app.store", () => {
  beforeEach(() => {
    useAppStore.setState({
      sidebarExpanded: true,
      commandPaletteOpen: false,
    })
  })

  it("has correct initial state", () => {
    const state = useAppStore.getState()
    expect(state.sidebarExpanded).toBe(true)
    expect(state.commandPaletteOpen).toBe(false)
  })

  it("toggleSidebar flips sidebarExpanded", () => {
    useAppStore.getState().toggleSidebar()
    expect(useAppStore.getState().sidebarExpanded).toBe(false)

    useAppStore.getState().toggleSidebar()
    expect(useAppStore.getState().sidebarExpanded).toBe(true)
  })

  it("setSidebarExpanded sets directly", () => {
    useAppStore.getState().setSidebarExpanded(false)
    expect(useAppStore.getState().sidebarExpanded).toBe(false)
  })

  it("setCommandPaletteOpen opens and closes", () => {
    useAppStore.getState().setCommandPaletteOpen(true)
    expect(useAppStore.getState().commandPaletteOpen).toBe(true)

    useAppStore.getState().setCommandPaletteOpen(false)
    expect(useAppStore.getState().commandPaletteOpen).toBe(false)
  })
})
