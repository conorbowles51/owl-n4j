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
})
