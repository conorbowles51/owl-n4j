import { beforeEach, describe, expect, it } from "vitest"
import { useEvidenceStore } from "./evidence.store"

describe("evidence search state", () => {
  beforeEach(() => {
    useEvidenceStore.getState().resetForCase(crypto.randomUUID())
  })

  it("preserves separate file and text queries while switching scopes", () => {
    const store = useEvidenceStore.getState()
    store.setFileSearchTerm("invoice.pdf")
    store.setSearchMode("text")
    useEvidenceStore.getState().setTextSearchTerm("AC-001_4%")
    useEvidenceStore.getState().setSearchMode("files")

    const state = useEvidenceStore.getState()
    expect(state.fileSearchTerm).toBe("invoice.pdf")
    expect(state.textSearchTerm).toBe("AC-001_4%")
    expect(state.textSearchOverlayOpen).toBe(false)
  })

  it("clears both search scopes when the case changes", () => {
    useEvidenceStore.getState().setFileSearchTerm("one")
    useEvidenceStore.getState().setTextSearchTerm("two")

    useEvidenceStore.getState().resetForCase(crypto.randomUUID())

    const state = useEvidenceStore.getState()
    expect(state.searchMode).toBe("files")
    expect(state.fileSearchTerm).toBe("")
    expect(state.textSearchTerm).toBe("")
    expect(state.textSearchOverlayOpen).toBe(false)
  })

  it("reveals a nested file atomically, clearing filters and preview anchors", () => {
    const store = useEvidenceStore.getState()
    store.setFileSearchTerm("hidden")
    store.setTypeFilter("audio")
    store.setStatusFilter("failed")
    store.setSearchMode("text")
    store.setTextSearchTerm("query")
    store.openDetail("previous", { page: 5 })
    store.selectAllFiles(["previous"])
    store.revealFile({
      file_id: "target",
      folder_id: "child",
      ancestor_ids: ["parent", "child"],
      file_offset: 500,
      file_limit: 250,
    })
    const state = useEvidenceStore.getState()
    expect(state).toMatchObject({
      currentFolderId: "child",
      filePage: 2,
      fileSearchTerm: "",
      typeFilter: "",
      statusFilter: "all",
      searchMode: "files",
      textSearchTerm: "",
      textSearchOverlayOpen: false,
      detailFileId: "target",
      detailOpen: true,
      detailAnchor: null,
      revealTargetFileId: "target",
    })
    expect([...state.expandedFolderIds]).toEqual(["parent", "child"])
    expect(state.selectedFileIds.size).toBe(0)
    store.finishReveal()
    expect(useEvidenceStore.getState().filePage).toBe(2)
    expect(useEvidenceStore.getState().revealTargetFileId).toBeNull()
  })

  it("reveals root files and resets pagination when browsing or filtering", () => {
    const store = useEvidenceStore.getState()
    store.setCurrentFolder("nested")
    store.revealFile({
      file_id: "root-file",
      folder_id: null,
      ancestor_ids: [],
      file_offset: 250,
      file_limit: 250,
    })
    expect(useEvidenceStore.getState().currentFolderId).toBeNull()
    for (const change of [
      () => store.setFileSearchTerm("test"),
      () => store.setStatusFilter("processed"),
      () => store.setTypeFilter("pdf"),
      () => store.setCurrentFolder("another"),
    ]) {
      store.setFilePage(3)
      change()
      expect(useEvidenceStore.getState().filePage).toBe(0)
      expect(useEvidenceStore.getState().revealTargetFileId).toBeNull()
    }
    store.setFilePage(4)
    store.resetForCase("next-case")
    expect(useEvidenceStore.getState().filePage).toBe(0)
  })
})


describe("evidence browsing preferences", () => {
  it("retains sort and width across cases while resetting result selection and page", async () => {
    const { readEvidencePreferences } = await import("./utils/preferences")
    useEvidenceStore.setState({ sortBy: "name", sortDirection: "asc", nameWidth: null })
    const store = useEvidenceStore.getState()
    store.selectAllFiles(["file"]); store.setFilePage(3); store.toggleSort("date")
    expect(useEvidenceStore.getState()).toMatchObject({ sortBy: "date", sortDirection: "desc", filePage: 0 })
    expect(useEvidenceStore.getState().selectedFileIds.size).toBe(0)
    store.toggleSort("date"); store.setNameWidth(900); store.resetForCase(crypto.randomUUID())
    expect(readEvidencePreferences()).toEqual({ sortBy: "date", sortDirection: "asc", nameWidth: 900 })
    expect(useEvidenceStore.getState()).toMatchObject({ sortBy: "date", nameWidth: 900 })
    store.setNameWidth(2000); expect(useEvidenceStore.getState().nameWidth).toBe(1600)
    store.setNameWidth(1); expect(useEvidenceStore.getState().nameWidth).toBe(180)
    store.setNameWidth(null); expect(readEvidencePreferences().nameWidth).toBeNull()
  })
  it("clears filename search on folder navigation and keeps the browse folder when clearing search", () => {
    const store = useEvidenceStore.getState()
    store.setCurrentFolder("browse"); store.setFileSearchTerm("report")
    expect(useEvidenceStore.getState().currentFolderId).toBe("browse")
    store.setFileSearchTerm("")
    expect(useEvidenceStore.getState().currentFolderId).toBe("browse")
    store.setFileSearchTerm("report"); store.setCurrentFolder("different")
    expect(useEvidenceStore.getState().fileSearchTerm).toBe("")
  })
})
