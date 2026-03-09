import { describe, it, expect, beforeEach } from "vitest"
import { useGraphStore } from "../graph.store"

describe("graph.store", () => {
  beforeEach(() => {
    useGraphStore.setState({
      selectedNodeKeys: new Set(),
      focusHistory: [],
      searchTerm: "",
      filters: {},
      viewSettings: {
        layout: "force",
        showLabels: true,
        showEdgeLabels: false,
      },
    })
  })

  describe("selection", () => {
    it("selectNodes replaces selection", () => {
      useGraphStore.getState().selectNodes(["a", "b"])
      const keys = useGraphStore.getState().selectedNodeKeys
      expect(keys.size).toBe(2)
      expect(keys.has("a")).toBe(true)
      expect(keys.has("b")).toBe(true)
    })

    it("addToSelection toggles a node", () => {
      useGraphStore.getState().addToSelection("a")
      expect(useGraphStore.getState().selectedNodeKeys.has("a")).toBe(true)

      useGraphStore.getState().addToSelection("a")
      expect(useGraphStore.getState().selectedNodeKeys.has("a")).toBe(false)
    })

    it("clearSelection empties selection", () => {
      useGraphStore.getState().selectNodes(["a", "b", "c"])
      useGraphStore.getState().clearSelection()
      expect(useGraphStore.getState().selectedNodeKeys.size).toBe(0)
    })
  })

  describe("focus history", () => {
    it("pushFocus adds entry", () => {
      useGraphStore.getState().pushFocus({ nodeKey: "n1", label: "Node 1" })
      expect(useGraphStore.getState().focusHistory).toHaveLength(1)
      expect(useGraphStore.getState().focusHistory[0].nodeKey).toBe("n1")
    })

    it("popFocus removes last entry", () => {
      useGraphStore.getState().pushFocus({ nodeKey: "n1", label: "Node 1" })
      useGraphStore.getState().pushFocus({ nodeKey: "n2", label: "Node 2" })
      useGraphStore.getState().popFocus()
      expect(useGraphStore.getState().focusHistory).toHaveLength(1)
      expect(useGraphStore.getState().focusHistory[0].nodeKey).toBe("n1")
    })
  })

  describe("search and filters", () => {
    it("setSearchTerm updates term", () => {
      useGraphStore.getState().setSearchTerm("test")
      expect(useGraphStore.getState().searchTerm).toBe("test")
    })

    it("setFilter adds/updates filter", () => {
      useGraphStore.getState().setFilter("person", true)
      expect(useGraphStore.getState().filters.person).toBe(true)

      useGraphStore.getState().setFilter("person", false)
      expect(useGraphStore.getState().filters.person).toBe(false)
    })
  })

  describe("view settings", () => {
    it("setViewSetting updates individual setting", () => {
      useGraphStore.getState().setViewSetting("layout", "radial")
      expect(useGraphStore.getState().viewSettings.layout).toBe("radial")

      useGraphStore.getState().setViewSetting("showLabels", false)
      expect(useGraphStore.getState().viewSettings.showLabels).toBe(false)
    })

    it("preserves other settings when updating one", () => {
      useGraphStore.getState().setViewSetting("layout", "hierarchical")
      expect(useGraphStore.getState().viewSettings.showLabels).toBe(true)
      expect(useGraphStore.getState().viewSettings.showEdgeLabels).toBe(false)
    })
  })
})
