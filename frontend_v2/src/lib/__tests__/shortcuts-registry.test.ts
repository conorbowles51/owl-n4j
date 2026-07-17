import { describe, expect, it } from "vitest"
import {
  CASE_VIEW_SHORTCUTS,
  SETTINGS_SHORTCUTS,
  SHORTCUTS,
} from "../shortcuts-registry"

describe("shortcuts registry", () => {
  it("keeps settings shortcuts limited to implemented shortcuts", () => {
    expect(SETTINGS_SHORTCUTS.length).toBeGreaterThan(0)
    expect(SETTINGS_SHORTCUTS.every((shortcut) => shortcut.implemented)).toBe(
      true
    )
  })

  it("uses the shared case-view order for display and route switching", () => {
    expect(CASE_VIEW_SHORTCUTS.map((shortcut) => shortcut.view)).toEqual([
      "graph",
      "timeline",
      "map",
      "table",
      "financial",
      "cellebrite",
      "profiles",
      "evidence",
    ])
    expect(CASE_VIEW_SHORTCUTS.map((shortcut) => shortcut.keys)).toEqual([
      "Ctrl/Cmd+Shift+1",
      "Ctrl/Cmd+Shift+2",
      "Ctrl/Cmd+Shift+3",
      "Ctrl/Cmd+Shift+4",
      "Ctrl/Cmd+Shift+5",
      "Ctrl/Cmd+Shift+6",
      "Ctrl/Cmd+Shift+7",
      "Ctrl/Cmd+Shift+8",
    ])
  })

  it("does not expose removed or browser-reserved shortcuts in settings", () => {
    const settingsKeys = SETTINGS_SHORTCUTS.map((shortcut) => shortcut.keys)
    const settingsDescriptions = SETTINGS_SHORTCUTS.map(
      (shortcut) => shortcut.description
    )

    expect(settingsKeys).not.toContain("Ctrl+K")
    expect(settingsKeys).not.toContain("Ctrl+S")
    expect(settingsKeys).not.toContain("Delete")
    expect(settingsKeys).not.toContain("Alt+Left")
    expect(settingsKeys).not.toContain("Alt+Right")
    expect(settingsKeys).not.toEqual(
      expect.arrayContaining([
        "Ctrl/Cmd+1",
        "Ctrl/Cmd+2",
        "Ctrl/Cmd+3",
        "Ctrl/Cmd+4",
        "Ctrl/Cmd+5",
        "Ctrl/Cmd+6",
        "Ctrl/Cmd+7",
        "Ctrl/Cmd+8",
      ])
    )
    expect(settingsDescriptions).not.toContain("Open command palette")
    expect(settingsDescriptions).not.toContain("Save (context-dependent)")
    expect(settingsDescriptions).not.toContain(
      "Delete selected (with confirmation)"
    )
  })

  it("has stable ids for every shortcut entry", () => {
    const ids = SHORTCUTS.map((shortcut) => shortcut.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})
